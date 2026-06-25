import re

def tokenize_tableau(s):
    """
    Tokenize a Tableau formula string into a list of (token_type, token_value) tuples.
    Handles strings, bracketed fields, numbers, words/keywords, and punctuation/operators.
    """
    token_pattern = re.compile(
        r"(?P<STRING>'[^']*'|\"[^\"]*\")|"
        r"(?P<FIELD>\[[^\]]*\])|"
        r"(?P<NUMBER>\d+(?:\.\d+)?)|"
        r"(?P<PUNCT>\{|\}|\(|\)|,|:|\+|-|\*|/|<=|>=|<>|<|>|=)|"
        r"(?P<WORD>[A-Za-z_][A-Za-z0-9_]*)|"
        r"(?P<SPACE>\s+)|"
        r"(?P<MISC>.)"
    )
    tokens = []
    for match in token_pattern.finditer(s):
        type_ = match.lastgroup
        val = match.group(type_)
        tokens.append((type_, val))
    return tokens

def tokenize_dax(s):
    """
    Tokenize a DAX formula string into a list of (token_type, token_value) tuples.
    Handles strings, table-prefixed or bare fields, numbers, words/keywords (with dots), and punctuation.
    """
    token_pattern = re.compile(
        r"(?P<FIELD>(?:'[^']+'|[A-Za-z0-9_]+)?\[[^\]]+\])|"
        r"(?P<STRING>\"[^\"]*\"|'[^']*')|"
        r"(?P<NUMBER>\d+(?:\.\d+)?)|"
        r"(?P<PUNCT>\{|\}|\(|\)|,|:|\+|-|\*|/|<=|>=|<>|<|>|=|\&\&|\|\|)|"
        r"(?P<WORD>[A-Za-z_][A-Za-z0-9_\.]*)|"
        r"(?P<SPACE>\s+)|"
        r"(?P<MISC>.)"
    )
    tokens = []
    for match in token_pattern.finditer(s):
        type_ = match.lastgroup
        val = match.group(type_)
        tokens.append((type_, val))
    return tokens

def format_expr_parts(parts):
    """
    Format a list of translated expression substrings into a single clean string.
    Minimizes unnecessary whitespace around function calls, commas, and parentheses.
    """
    res = ""
    for i, part in enumerate(parts):
        if i == 0:
            res = part
        elif part in (',', '.', ')'):
            res += part
        elif part == '(':
            prev = parts[i-1]
            # No space before opening parenthesis if it follows a function name or a field
            if prev.isidentifier() or prev.endswith(']'):
                res += part
            else:
                res += " " + part
        elif res and res[-1] in ('(', '.'):
            res += part
        else:
            res += " " + part
    return res

# Keywords and functions recognized as standard in Tableau / DAX
ALLOWED_TABLEAU_WORDS = {
    'AND', 'OR', 'NOT', 'TRUE', 'FALSE', 'NULL',
    'IF', 'THEN', 'ELSEIF', 'ELSE', 'END', 'CASE', 'WHEN',
    'FIXED', 'INCLUDE', 'EXCLUDE'
}

ALLOWED_DAX_WORDS = {
    'AND', 'OR', 'NOT', 'TRUE', 'FALSE', 'BLANK',
    'IF', 'SWITCH', 'ALLEXCEPT', 'REMOVEFILTERS', 'ALL'
}

class TableauToDaxParser:
    def __init__(self, tokens, field_table_map):
        self.tokens = [t for t in tokens if t[0] != 'SPACE']
        self.field_table_map = field_table_map
        self.pos = 0
        self.notes = []
        self.has_complex_rule = False

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return (None, None)

    def advance(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def match_word(self, word):
        tok = self.peek()
        if tok[0] == 'WORD' and tok[1].upper() == word.upper():
            self.pos += 1
            return tok
        return None

    def match_punct(self, punct):
        tok = self.peek()
        if tok[0] == 'PUNCT' and tok[1] == punct:
            self.pos += 1
            return tok
        return None

    def resolve_field(self, field_name):
        table = "Table"
        if field_name in self.field_table_map:
            table = self.field_table_map[field_name]
        elif self.field_table_map:
            table = list(self.field_table_map.values())[0]
        if not table.startswith("'"):
            table = f"'{table}'"
        return f"{table}[{field_name}]"

    def get_table_from_fields(self, fields):
        table = "Table"
        for f in fields:
            if f in self.field_table_map:
                table = self.field_table_map[f]
                break
        else:
            if self.field_table_map:
                table = list(self.field_table_map.values())[0]
        if not table.startswith("'"):
            table = f"'{table}'"
        return table

    def get_table_from_str(self, s):
        table = "Table"
        for tbl in self.field_table_map.values():
            if tbl in s:
                table = tbl
                break
        else:
            match = re.search(r'([A-Za-z0-9_]+)\[', s)
            if match:
                table = match.group(1)
        if not table.startswith("'"):
            table = f"'{table}'"
        return table

    def _is_simple_column_ref(self, s: str) -> bool:
        """Return True if s is a plain DAX column reference like 'Table'[Col] or Table[Col].
        Returns False if the expression contains any function calls, operators, or keywords
        that would make it incompatible with SUM/MIN/MAX/etc. (which require a column ref)."""
        s = s.strip()
        # Matches: optional 'Table' or Table prefix, then [Column]
        return bool(re.fullmatch(r"(?:'[^']+'|[A-Za-z0-9_ ]+)?\[[^\]]+\]", s))

    def parse_expression(self, boundaries=set()):
        expr_parts = []
        while self.pos < len(self.tokens):
            tok = self.peek()
            if tok[0] == 'WORD' and tok[1].upper() in boundaries:
                break
            if tok[0] == 'PUNCT' and tok[1] in boundaries:
                break
            term = self.parse_term()
            expr_parts.append(term)
        return format_expr_parts(expr_parts)

    def parse_term(self):
        tok = self.peek()
        if not tok[0]:
            return ""

        if tok[0] == 'STRING':
            self.advance()
            val = tok[1]
            content = val[1:-1]
            escaped = content.replace('"', '""')
            return f'"{escaped}"'

        if tok[0] == 'FIELD':
            self.advance()
            field_name = tok[1][1:-1]
            return self.resolve_field(field_name)

        if tok[0] == 'PUNCT' and tok[1] == '(':
            self.advance()
            inner = self.parse_expression(boundaries={')'})
            self.match_punct(')')
            return f"({inner})"

        if tok[0] == 'PUNCT' and tok[1] == '{':
            return self.parse_lod()

        if tok[0] == 'WORD':
            word_upper = tok[1].upper()

            # Check if word is unrecognized
            is_func = False
            if self.pos + 1 < len(self.tokens):
                is_func = (self.tokens[self.pos + 1][1] == '(')

            if not is_func:
                if word_upper not in ALLOWED_TABLEAU_WORDS and word_upper not in ('TODAY', 'NOW'):
                    self.notes.append(f"Unrecognized identifier: {tok[1]}")

            if word_upper == 'IF' and not is_func:
                self.advance()
                return self.parse_if_statement()

            if word_upper == 'CASE':
                self.advance()
                return self.parse_case_statement()

            if word_upper == 'TODAY' and not is_func:
                self.advance()
                return "TODAY()"

            if word_upper == 'NOW' and not is_func:
                self.advance()
                return "NOW()"

            if word_upper == 'NULL' and not is_func:
                self.advance()
                return "BLANK()"

            if is_func:
                self.advance()
                return self.parse_function_call(tok[1])

            self.advance()
            return tok[1]

        self.advance()
        return tok[1]

    def parse_if_statement(self):
        self.has_complex_rule = True
        cond = self.parse_expression(boundaries={'THEN'})
        self.match_word('THEN')
        then_expr = self.parse_expression(boundaries={'ELSEIF', 'ELSE', 'END'})

        elseif_cases = []
        while self.match_word('ELSEIF'):
            ei_cond = self.parse_expression(boundaries={'THEN'})
            self.match_word('THEN')
            ei_then = self.parse_expression(boundaries={'ELSEIF', 'ELSE', 'END'})
            elseif_cases.append((ei_cond, ei_then))

        else_expr = None
        if self.match_word('ELSE'):
            else_expr = self.parse_expression(boundaries={'END'})

        self.match_word('END')

        if else_expr:
            current_else = else_expr
        else:
            current_else = "BLANK()" if elseif_cases else None

        for ei_cond, ei_then in reversed(elseif_cases):
            if current_else:
                current_else = f"IF({ei_cond}, {ei_then}, {current_else})"
            else:
                current_else = f"IF({ei_cond}, {ei_then})"

        if current_else:
            return f"IF({cond}, {then_expr}, {current_else})"
        else:
            return f"IF({cond}, {then_expr})"

    def parse_case_statement(self):
        self.has_complex_rule = True
        case_val = self.parse_expression(boundaries={'WHEN'})

        cases = []
        while self.match_word('WHEN'):
            when_val = self.parse_expression(boundaries={'THEN'})
            self.match_word('THEN')
            then_val = self.parse_expression(boundaries={'WHEN', 'ELSE', 'END'})
            cases.append((when_val, then_val))

        else_val = None
        if self.match_word('ELSE'):
            else_val = self.parse_expression(boundaries={'END'})

        self.match_word('END')

        parts = [case_val]
        for w, t in cases:
            parts.append(w)
            parts.append(t)
        if else_val:
            parts.append(else_val)

        return f"SWITCH({', '.join(parts)})"

    def parse_lod(self):
        self.has_complex_rule = True
        self.advance()  # consume '{'

        lod_tokens = []
        depth = 1
        while self.pos < len(self.tokens):
            tok = self.peek()
            if tok[1] == '{':
                depth += 1
            elif tok[1] == '}':
                depth -= 1
                if depth == 0:
                    self.advance()  # consume '}'
                    break
            lod_tokens.append(self.advance())

        colon_idx = -1
        paren_depth = 0
        for idx, tok in enumerate(lod_tokens):
            if tok[1] == '(':
                paren_depth += 1
            elif tok[1] == ')':
                paren_depth -= 1
            elif tok[1] == ':' and paren_depth == 0:
                colon_idx = idx
                break

        if colon_idx != -1:
            lhs_tokens = lod_tokens[:colon_idx]
            rhs_tokens = lod_tokens[colon_idx+1:]
        else:
            lhs_tokens = lod_tokens
            rhs_tokens = []

        if not lhs_tokens:
            return "{}"

        lod_keyword = ""
        if lhs_tokens[0][0] == 'WORD':
            lod_keyword = lhs_tokens[0][1].upper()

        dim_fields = []
        for tok in lhs_tokens:
            if tok[0] == 'FIELD':
                dim_fields.append(tok[1][1:-1])

        # Parse RHS using a sub-parser
        rhs_parser = TableauToDaxParser(rhs_tokens, self.field_table_map)
        translated_expr = rhs_parser.parse_full()
        self.notes.extend(rhs_parser.notes)
        self.has_complex_rule = self.has_complex_rule or rhs_parser.has_complex_rule

        T = self.get_table_from_fields(dim_fields)

        if lod_keyword == 'FIXED':
            if not dim_fields:
                return f"CALCULATE({translated_expr}, ALL({T}))"
            else:
                dim_cols = ", ".join([f"{T}[{d}]" for d in dim_fields])
                return f"CALCULATE({translated_expr}, ALLEXCEPT({T}, {dim_cols}))"
        elif lod_keyword == 'EXCLUDE':
            dim_cols = ", ".join([f"{T}[{d}]" for d in dim_fields])
            return f"CALCULATE({translated_expr}, REMOVEFILTERS({dim_cols}))"
        elif lod_keyword == 'INCLUDE':
            if len(dim_fields) == 1:
                dim_col = f"{T}[{dim_fields[0]}]"
                return f"AVERAGEX(VALUES({dim_col}), CALCULATE({translated_expr}))"
            else:
                dim_cols = ", ".join([f"{T}[{d}]" for d in dim_fields])
                return f"AVERAGEX(SUMMARIZE({T}, {dim_cols}), CALCULATE({translated_expr}))"
        else:
            self.notes.append(f"Unknown LOD keyword: {lod_keyword}")
            return f"{{ {lod_keyword} : {translated_expr} }}"

    def parse_function_call(self, func_name):
        self.advance()  # consume '('

        args = []
        if self.peek()[1] != ')':
            while True:
                arg_str = self.parse_expression(boundaries={',', ')'})
                args.append(arg_str)
                next_tok = self.peek()
                if next_tok[1] == ',':
                    self.advance()
                elif next_tok[1] == ')':
                    self.advance()
                    break
                else:
                    break
        else:
            self.advance()  # consume ')'

        func_name_upper = func_name.upper()

        if func_name_upper == 'RUNNING_SUM':
            self.has_complex_rule = True
            return f"CALCULATE({args[0]}, FILTER(ALL(DimDate), DimDate[Date] <= MAX(DimDate[Date])))"
        elif func_name_upper == 'WINDOW_AVG':
            self.has_complex_rule = True
            return f"AVERAGEX(ALL(DimDate[Month]), CALCULATE({args[0]}))"
        elif func_name_upper == 'WINDOW_SUM':
            self.has_complex_rule = True
            return f"CALCULATE({args[0]}, ALL(DimDate[Month]))"
        elif func_name_upper == 'RANK':
            self.has_complex_rule = True
            table_name = self.get_table_from_str(args[0])
            return f"RANKX(ALL({table_name}), CALCULATE({args[0]}))"
        elif func_name_upper == 'PERCENT_OF_TOTAL':
            self.has_complex_rule = True
            table_name = self.get_table_from_str(args[0])
            return f"DIVIDE({args[0]}, CALCULATE({args[0]}, ALL({table_name})))"
        elif func_name_upper == 'SUM':
            arg = args[0] if args else "0"
            if self._is_simple_column_ref(arg):
                return f"SUM({arg})"
            else:
                self.has_complex_rule = True
                table_name = self.get_table_from_str(arg)
                return f"SUMX({table_name}, {arg})"
        elif func_name_upper == 'AVG':
            arg = args[0] if args else "0"
            if self._is_simple_column_ref(arg):
                return f"AVERAGE({arg})"
            else:
                self.has_complex_rule = True
                table_name = self.get_table_from_str(arg)
                return f"AVERAGEX({table_name}, {arg})"
        elif func_name_upper == 'COUNTD':
            arg = args[0] if args else "0"
            if self._is_simple_column_ref(arg):
                return f"DISTINCTCOUNT({arg})"
            else:
                self.has_complex_rule = True
                table_name = self.get_table_from_str(arg)
                return f"DISTINCTCOUNT({arg})"
        elif func_name_upper == 'COUNT':
            arg = args[0] if args else "0"
            if self._is_simple_column_ref(arg):
                return f"COUNT({arg})"
            else:
                self.has_complex_rule = True
                table_name = self.get_table_from_str(arg)
                return f"COUNTX({table_name}, {arg})"
        elif func_name_upper == 'MIN':
            arg = args[0] if args else "0"
            if self._is_simple_column_ref(arg):
                return f"MIN({arg})"
            else:
                self.has_complex_rule = True
                table_name = self.get_table_from_str(arg)
                return f"MINX({table_name}, {arg})"
        elif func_name_upper == 'MAX':
            arg = args[0] if args else "0"
            if self._is_simple_column_ref(arg):
                return f"MAX({arg})"
            else:
                self.has_complex_rule = True
                table_name = self.get_table_from_str(arg)
                return f"MAXX({table_name}, {arg})"
        elif func_name_upper == 'MEDIAN':
            arg = args[0] if args else "0"
            if self._is_simple_column_ref(arg):
                return f"MEDIAN({arg})"
            else:
                self.has_complex_rule = True
                table_name = self.get_table_from_str(arg)
                return f"MEDIANX({table_name}, {arg})"
        elif func_name_upper == 'STDEV':
            arg = args[0] if args else "0"
            if self._is_simple_column_ref(arg):
                return f"STDEV.S({arg})"
            else:
                self.has_complex_rule = True
                table_name = self.get_table_from_str(arg)
                return f"STDEVX.S({table_name}, {arg})"
        elif func_name_upper == 'ZN':
            self.has_complex_rule = True
            return f"IF(ISBLANK({args[0]}), 0, {args[0]})"
        elif func_name_upper == 'ISNULL':
            return f"ISBLANK({args[0]})"
        elif func_name_upper == 'IFNULL':
            self.has_complex_rule = True
            return f"IF(ISBLANK({args[0]}), {args[1]}, {args[0]})"
        elif func_name_upper == 'IIF':
            return f"IF({args[0]}, {args[1]}, {args[2]})"
        elif func_name_upper == 'YEAR':
            return f"YEAR({args[0]})"
        elif func_name_upper == 'MONTH':
            return f"MONTH({args[0]})"
        elif func_name_upper == 'DAY':
            return f"DAY({args[0]})"
        elif func_name_upper == 'QUARTER':
            return f"QUARTER({args[0]})"
        elif func_name_upper == 'DATEPART':
            part = args[0].strip('\'"')
            date_expr = args[1]
            part_upper = part.upper()
            if part_upper in ('YEAR', 'YYYY'):
                return f"YEAR({date_expr})"
            elif part_upper in ('MONTH', 'MM'):
                return f"MONTH({date_expr})"
            elif part_upper in ('QUARTER', 'QQ', 'Q'):
                return f"QUARTER({date_expr})"
            elif part_upper in ('WEEK', 'WW', 'WK'):
                return f"WEEKNUM({date_expr})"
            elif part_upper in ('WEEKDAY', 'DW', 'DAYOFWEEK'):
                return f"WEEKDAY({date_expr})"
            else:
                self.notes.append(f"Unknown date part '{part}' in DATEPART.")
                return f"DATEPART({args[0]}, {args[1]})"
        elif func_name_upper == 'DATEADD':
            part = args[0].strip('\'"').upper()
            interval = args[1]
            date_expr = args[2]
            dax_intervals = {
                'YEAR': 'YEAR', 'YYYY': 'YEAR', 'YY': 'YEAR',
                'QUARTER': 'QUARTER', 'QQ': 'QUARTER', 'Q': 'QUARTER',
                'MONTH': 'MONTH', 'MM': 'MONTH', 'M': 'MONTH',
                'DAY': 'DAY', 'DD': 'DAY', 'D': 'DAY'
            }
            dax_part = dax_intervals.get(part, part)
            return f"DATEADD({date_expr}, {interval}, {dax_part})"
        elif func_name_upper == 'DATEDIFF':
            part = args[0].strip('\'"').upper()
            date1 = args[1]
            date2 = args[2]
            dax_intervals = {
                'YEAR': 'YEAR', 'YYYY': 'YEAR', 'YY': 'YEAR',
                'QUARTER': 'QUARTER', 'QQ': 'QUARTER', 'Q': 'QUARTER',
                'MONTH': 'MONTH', 'MM': 'MONTH', 'M': 'MONTH',
                'DAY': 'DAY', 'DD': 'DAY', 'D': 'DAY',
                'HOUR': 'HOUR', 'MINUTE': 'MINUTE', 'SECOND': 'SECOND'
            }
            dax_part = dax_intervals.get(part, part)
            return f"DATEDIFF({date1}, {date2}, {dax_part})"
        elif func_name_upper == 'LEN':
            return f"LEN({args[0]})"
        elif func_name_upper == 'TRIM':
            return f"TRIM({args[0]})"
        elif func_name_upper == 'UPPER':
            return f"UPPER({args[0]})"
        elif func_name_upper == 'LOWER':
            return f"LOWER({args[0]})"
        elif func_name_upper == 'LEFT':
            return f"LEFT({args[0]}, {args[1]})"
        elif func_name_upper == 'RIGHT':
            return f"RIGHT({args[0]}, {args[1]})"
        elif func_name_upper == 'MID':
            return f"MID({args[0]}, {args[1]}, {args[2]})"
        elif func_name_upper == 'CONTAINS':
            return f"CONTAINSSTRING({args[0]}, {args[1]})"
        elif func_name_upper == 'STARTSWITH':
            return f"LEFT({args[0]}, LEN({args[1]})) = {args[1]}"
        elif func_name_upper == 'ENDSWITH':
            return f"RIGHT({args[0]}, LEN({args[1]})) = {args[1]}"
        elif func_name_upper == 'STR':
            return f'TEXT({args[0]}, "")'
        elif func_name_upper == 'INT':
            return f"INT({args[0]})"
        elif func_name_upper == 'FLOAT':
            return f"FLOAT({args[0]})"
        elif func_name_upper == 'REPLACE':
            return f"SUBSTITUTE({args[0]}, {args[1]}, {args[2]})"
        elif func_name_upper == 'FIND':
            if len(args) == 2:
                return f"FIND({args[1]}, {args[0]}, 1, 0)"
            else:
                return f"FIND({args[1]}, {args[0]}, {args[2]}, 0)"
        elif func_name_upper == 'ABS':
            return f"ABS({args[0]})"
        elif func_name_upper == 'ROUND':
            return f"ROUND({args[0]}, {args[1]})"
        elif func_name_upper == 'CEILING':
            return f"CEILING({args[0]}, 1)"
        elif func_name_upper == 'FLOOR':
            return f"FLOOR({args[0]}, 1)"
        elif func_name_upper == 'POWER':
            return f"POWER({args[0]}, {args[1]})"
        elif func_name_upper == 'SQRT':
            return f"SQRT({args[0]})"
        elif func_name_upper == 'EXP':
            return f"EXP({args[0]})"
        elif func_name_upper == 'LN':
            return f"LN({args[0]})"
        elif func_name_upper == 'LOG':
            if len(args) == 1:
                return f"LOG({args[0]}, 10)"
            else:
                return f"LOG({args[0]}, {args[1]})"
        elif func_name_upper in ('RANK_PERCENTILE', 'PERCENTILE_RANK'):
            self.has_complex_rule = True
            # Tableau: RANK_PERCENTILE(expr, 'asc'|'desc')
            # The 2nd arg is sort direction string — drop it, use PERCENTILEX in DAX
            expr = args[0] if args else "0"
            table_name = self.get_table_from_str(expr)
            if not table_name:
                table_name = list(self.field_table_map.values())[0] if self.field_table_map else "'Table'"
            return f"DIVIDE(RANKX(ALL('{table_name}'), {expr},, ASC), COUNTROWS(ALL('{table_name}')))"
        elif func_name_upper in ('RUNNING_AVG',):
            self.has_complex_rule = True
            return f"AVERAGEX(FILTER(ALL(DimDate), DimDate[Date] <= MAX(DimDate[Date])), {args[0]})"
        elif func_name_upper in ('RUNNING_COUNT',):
            self.has_complex_rule = True
            return f"CALCULATE(COUNT({args[0]}), FILTER(ALL(DimDate), DimDate[Date] <= MAX(DimDate[Date])))"
        elif func_name_upper in ('RUNNING_MIN',):
            self.has_complex_rule = True
            return f"MINX(FILTER(ALL(DimDate), DimDate[Date] <= MAX(DimDate[Date])), {args[0]})"
        elif func_name_upper in ('RUNNING_MAX',):
            self.has_complex_rule = True
            return f"MAXX(FILTER(ALL(DimDate), DimDate[Date] <= MAX(DimDate[Date])), {args[0]})"
        elif func_name_upper in ('INDEX',):
            self.has_complex_rule = True
            return f"RANKX(ALL(), 1, 1, ASC)"
        elif func_name_upper in ('TOTAL',):
            self.has_complex_rule = True
            expr = args[0] if args else "0"
            table_name = self.get_table_from_str(expr)
            if not table_name:
                table_name = list(self.field_table_map.values())[0] if self.field_table_map else "'Table'"
            return f"CALCULATE({expr}, ALL('{table_name}'))"
        elif func_name_upper in ('WINDOW_MAX',):
            self.has_complex_rule = True
            return f"MAXX(ALL(DimDate[Month]), CALCULATE({args[0]}))"
        elif func_name_upper in ('WINDOW_MIN',):
            self.has_complex_rule = True
            return f"MINX(ALL(DimDate[Month]), CALCULATE({args[0]}))"
        elif func_name_upper in ('WINDOW_COUNT',):
            self.has_complex_rule = True
            return f"CALCULATE(COUNT({args[0]}), ALL(DimDate[Month]))"
        elif func_name_upper in ('WINDOW_MEDIAN',):
            self.has_complex_rule = True
            return f"MEDIANX(ALL(DimDate[Month]), CALCULATE({args[0]}))"
        elif func_name_upper in ('LOOKUP',):
            self.has_complex_rule = True
            self.notes.append("LOOKUP has no direct DAX equivalent; approximated as the raw expression.")
            return args[0] if args else "BLANK()"
        elif func_name_upper in ('PREVIOUS_VALUE', 'FIRST', 'LAST', 'SIZE',
                                 'SCRIPT_INT', 'SCRIPT_STR', 'SCRIPT_REAL', 'SCRIPT_BOOL'):
            self.has_complex_rule = True
            self.notes.append(f"{func_name} has no DAX equivalent; replaced with BLANK().")
            return "BLANK()"
        else:
            self.notes.append(f"Function {func_name} has no exact DAX translation; kept as-is.")
            return f"{func_name}({', '.join(args)})"

    def parse_full(self):
        parts = []
        while self.pos < len(self.tokens):
            parts.append(self.parse_term())
        return format_expr_parts(parts)


class DaxToTableauParser:
    def __init__(self, tokens, field_table_map):
        self.tokens = [t for t in tokens if t[0] != 'SPACE']
        self.field_table_map = field_table_map
        self.pos = 0
        self.notes = []
        self.has_complex_rule = False

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return (None, None)

    def advance(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def match_word(self, word):
        tok = self.peek()
        if tok[0] == 'WORD' and tok[1].upper() == word.upper():
            self.pos += 1
            return tok
        return None

    def match_punct(self, punct):
        tok = self.peek()
        if tok[0] == 'PUNCT' and tok[1] == punct:
            self.pos += 1
            return tok
        return None

    def parse_expression(self, boundaries=set()):
        expr_parts = []
        while self.pos < len(self.tokens):
            tok = self.peek()
            if tok[0] == 'WORD' and tok[1].upper() in boundaries:
                break
            if tok[0] == 'PUNCT' and tok[1] in boundaries:
                break
            term = self.parse_term()
            expr_parts.append(term)
        return format_expr_parts(expr_parts)

    def parse_term(self):
        tok = self.peek()
        if not tok[0]:
            return ""

        if tok[0] == 'STRING':
            self.advance()
            val = tok[1]
            content = val[1:-1]
            escaped = content.replace("'", "\\'")
            return f"'{escaped}'"

        if tok[0] == 'FIELD':
            self.advance()
            val = tok[1]
            match = re.search(r'\[([^\]]+)\]', val)
            if match:
                return f"[{match.group(1)}]"
            return val

        if tok[0] == 'PUNCT' and tok[1] == '(':
            self.advance()
            inner = self.parse_expression(boundaries={')'})
            self.match_punct(')')
            return f"({inner})"

        if tok[0] == 'WORD':
            word_upper = tok[1].upper()
            is_func = False
            if self.pos + 1 < len(self.tokens):
                is_func = (self.tokens[self.pos + 1][1] == '(')

            if not is_func:
                if word_upper not in ALLOWED_DAX_WORDS and word_upper not in ('TODAY', 'NOW'):
                    self.notes.append(f"Unrecognized identifier: {tok[1]}")

            if is_func:
                self.advance()
                return self.parse_function_call(tok[1])

            self.advance()
            return tok[1]

        self.advance()
        return tok[1]

    def parse_function_call(self, func_name):
        self.advance()  # consume '('

        func_name_upper = func_name.upper()

        if func_name_upper == 'CALCULATE':
            self.has_complex_rule = True
            expr = self.parse_expression(boundaries={',', ')'})
            
            next_tok = self.peek()
            if next_tok[1] == ',':
                self.advance()  # consume ','
                
                filter_tok = self.peek()
                if filter_tok[0] == 'WORD' and filter_tok[1].upper() == 'ALLEXCEPT':
                    self.advance()
                    self.match_punct('(')
                    # Table name
                    self.advance()
                    
                    cols = []
                    while self.peek()[1] == ',':
                        self.advance()
                        col_str = self.parse_expression(boundaries={',', ')'})
                        cols.append(col_str)
                    self.match_punct(')')  # consume ')' of ALLEXCEPT
                    self.match_punct(')')  # consume ')' of CALCULATE
                    
                    dim_cols = ", ".join(cols)
                    return f"{{ FIXED {dim_cols} : {expr} }}"
                    
                elif filter_tok[0] == 'WORD' and filter_tok[1].upper() == 'REMOVEFILTERS':
                    self.advance()
                    self.match_punct('(')
                    col_first = self.parse_expression(boundaries={',', ')'})
                    cols = [col_first]
                    while self.peek()[1] == ',':
                        self.advance()
                        col_str = self.parse_expression(boundaries={',', ')'})
                        cols.append(col_str)
                    self.match_punct(')')  # consume ')' of REMOVEFILTERS
                    self.match_punct(')')  # consume ')' of CALCULATE
                    
                    dim_cols = ", ".join(cols)
                    return f"{{ EXCLUDE {dim_cols} : {expr} }}"
                    
                else:
                    filters = []
                    while True:
                        filt_str = self.parse_expression(boundaries={',', ')'})
                        filters.append(filt_str)
                        if self.peek()[1] == ',':
                            self.advance()
                        elif self.peek()[1] == ')':
                            self.advance()
                            break
                        else:
                            break
                    self.notes.append("CALCULATE with custom filters cannot be deterministically translated; kept expression only.")
                    return expr
            else:
                self.match_punct(')')
                return expr

        # Parse args for other functions
        args = []
        if self.peek()[1] != ')':
            while True:
                arg_str = self.parse_expression(boundaries={',', ')'})
                args.append(arg_str)
                next_tok = self.peek()
                if next_tok[1] == ',':
                    self.advance()
                elif next_tok[1] == ')':
                    self.advance()
                    break
                else:
                    break
        else:
            self.advance()  # consume ')'

        if func_name_upper == 'DIVIDE':
            if len(args) == 3:
                return f"IIF({args[1]} = 0, {args[2]}, {args[0]} / {args[1]})"
            else:
                return f"IIF({args[1]} = 0, NULL, {args[0]} / {args[1]})"
        elif func_name_upper == 'SAMEPERIODLASTYEAR':
            self.has_complex_rule = True
            return f"DATEADD('year', -1, {args[0]})"
        elif func_name_upper == 'TOTALYTD':
            self.has_complex_rule = True
            self.notes.append("TOTALYTD translation to RUNNING_SUM: Note that TOTALYTD resets at the end of each year, whereas RUNNING_SUM runs continuously unless partitioned.")
            return f"RUNNING_SUM({args[0]})"
        elif func_name_upper == 'RANKX':
            self.has_complex_rule = True
            if len(args) >= 2:
                return f"RANK({args[1]})"
            else:
                return f"RANK({args[0]})"
        elif func_name_upper == 'COALESCE':
            res = args[-1]
            for arg in reversed(args[:-1]):
                res = f"IFNULL({arg}, {res})"
            return res
        elif func_name_upper == 'CONCATENATE':
            return f"{args[0]} + {args[1]}"
        elif func_name_upper == 'FORMAT':
            self.has_complex_rule = True
            fmt = args[1].strip('\'"').upper()
            if fmt in ('YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS'):
                return f"STR(DATEPART('year', {args[0]})) + '-' + STR(DATEPART('month', {args[0]})) + '-' + STR(DATEPART('day', {args[0]}))"
            elif fmt == 'YYYY-MM':
                return f"STR(DATEPART('year', {args[0]})) + '-' + STR(DATEPART('month', {args[0]}))"
            else:
                self.notes.append(f"FORMAT with pattern '{fmt}' not directly translatable; used STR fallback.")
                return f"STR({args[0]})"
        elif func_name_upper == 'SUM':
            return f"SUM({args[0]})"
        elif func_name_upper == 'AVERAGE':
            return f"AVG({args[0]})"
        elif func_name_upper == 'DISTINCTCOUNT':
            return f"COUNTD({args[0]})"
        elif func_name_upper == 'COUNT':
            return f"COUNT({args[0]})"
        elif func_name_upper == 'MIN':
            return f"MIN({args[0]})"
        elif func_name_upper == 'MAX':
            return f"MAX({args[0]})"
        elif func_name_upper == 'MEDIAN':
            return f"MEDIAN({args[0]})"
        elif func_name_upper in ('STDEV.S', 'STDEV'):
            return f"STDEV({args[0]})"
        elif func_name_upper == 'ISBLANK':
            return f"ISNULL({args[0]})"
        elif func_name_upper == 'BLANK':
            return "NULL"
        elif func_name_upper == 'IF':
            cond = args[0]
            # ZN Check
            if cond.startswith("ISNULL(") and cond.endswith(")") and args[1] == "0":
                inner = cond[7:-1]
                if len(args) > 2 and inner == args[2]:
                    return f"ZN({inner})"
            # IFNULL Check
            if cond.startswith("ISNULL(") and cond.endswith(")"):
                inner = cond[7:-1]
                if len(args) > 2 and inner == args[2]:
                    return f"IFNULL({inner}, {args[1]})"

            if len(args) == 3:
                return f"IIF({args[0]}, {args[1]}, {args[2]})"
            else:
                return f"IIF({args[0]}, {args[1]}, NULL)"
        elif func_name_upper == 'SWITCH':
            self.has_complex_rule = True
            expr = args[0]
            cases = args[1:]
            case_str_list = []
            for i in range(0, len(cases) - 1, 2):
                val = cases[i]
                res = cases[i+1]
                case_str_list.append(f"WHEN {val} THEN {res}")
            if len(cases) % 2 != 0:
                default_val = cases[-1]
                case_str_list.append(f"ELSE {default_val}")
            return f"CASE {expr} {' '.join(case_str_list)} END"
        elif func_name_upper == 'YEAR':
            return f"YEAR({args[0]})"
        elif func_name_upper == 'MONTH':
            return f"MONTH({args[0]})"
        elif func_name_upper == 'DAY':
            return f"DAY({args[0]})"
        elif func_name_upper == 'QUARTER':
            return f"QUARTER({args[0]})"
        elif func_name_upper == 'TODAY':
            return "TODAY()"
        elif func_name_upper == 'NOW':
            return "NOW()"
        elif func_name_upper == 'DATEADD':
            date_expr = args[0]
            val = args[1]
            interval = args[2].strip('\'"').lower()
            tab_interval = 'year' if 'year' in interval else ('month' if 'month' in interval else ('day' if 'day' in interval else ('quarter' if 'quarter' in interval else interval)))
            return f"DATEADD('{tab_interval}', {val}, {date_expr})"
        elif func_name_upper == 'DATEDIFF':
            date1 = args[0]
            date2 = args[1]
            interval = args[2].strip('\'"').lower()
            tab_interval = 'year' if 'year' in interval else ('month' if 'month' in interval else ('day' if 'day' in interval else ('quarter' if 'quarter' in interval else interval)))
            return f"DATEDIFF('{tab_interval}', {date1}, {date2})"
        elif func_name_upper == 'LEN':
            return f"LEN({args[0]})"
        elif func_name_upper == 'TRIM':
            return f"TRIM({args[0]})"
        elif func_name_upper == 'UPPER':
            return f"UPPER({args[0]})"
        elif func_name_upper == 'LOWER':
            return f"LOWER({args[0]})"
        elif func_name_upper == 'LEFT':
            return f"LEFT({args[0]}, {args[1]})"
        elif func_name_upper == 'RIGHT':
            return f"RIGHT({args[0]}, {args[1]})"
        elif func_name_upper == 'MID':
            return f"MID({args[0]}, {args[1]}, {args[2]})"
        elif func_name_upper == 'CONTAINSSTRING':
            return f"CONTAINS({args[0]}, {args[1]})"
        elif func_name_upper == 'TEXT':
            return f"STR({args[0]})"
        elif func_name_upper == 'INT':
            return f"INT({args[0]})"
        elif func_name_upper == 'FLOAT':
            return f"FLOAT({args[0]})"
        elif func_name_upper == 'SUBSTITUTE':
            return f"REPLACE({args[0]}, {args[1]}, {args[2]})"
        elif func_name_upper == 'FIND':
            if len(args) >= 3:
                return f"FIND({args[1]}, {args[0]}, {args[2]})"
            else:
                return f"FIND({args[1]}, {args[0]})"
        elif func_name_upper == 'ABS':
            return f"ABS({args[0]})"
        elif func_name_upper == 'ROUND':
            return f"ROUND({args[0]}, {args[1]})"
        elif func_name_upper == 'CEILING':
            return f"CEILING({args[0]})"
        elif func_name_upper == 'FLOOR':
            return f"FLOOR({args[0]})"
        elif func_name_upper == 'POWER':
            return f"POWER({args[0]}, {args[1]})"
        elif func_name_upper == 'SQRT':
            return f"SQRT({args[0]})"
        elif func_name_upper == 'EXP':
            return f"EXP({args[0]})"
        elif func_name_upper == 'LN':
            return f"LN({args[0]})"
        elif func_name_upper == 'LOG':
            if len(args) == 1:
                return f"LOG({args[0]})"
            else:
                return f"LOG({args[0]}, {args[1]})"
        else:
            self.notes.append(f"Function {func_name} has no exact Tableau translation; kept as-is.")
            return f"{func_name}({', '.join(args)})"

    def parse_full(self):
        parts = []
        while self.pos < len(self.tokens):
            parts.append(self.parse_term())
        
        translated = format_expr_parts(parts)
        
        # Post-processing replacements for STARTSWITH and ENDSWITH
        translated = re.sub(
            r"LEFT\(([^,]+),\s*LEN\(([^)]+)\)\)\s*=\s*\2",
            r"STARTSWITH(\1, \2)",
            translated
        )
        translated = re.sub(
            r"RIGHT\(([^,]+),\s*LEN\(([^)]+)\)\)\s*=\s*\2",
            r"ENDSWITH(\1, \2)",
            translated
        )
        return translated


def translate_tableau_to_dax(formula, field_table_map):
    """
    Translate a Tableau formula to a DAX formula using deterministic rules.
    
    Parameters:
    - formula (str): The Tableau formula.
    - field_table_map (dict): Mapping of {field_name: table_name} to resolve field prefixes.
    
    Returns:
    - (translated_str, confidence, notes)
    """
    if not formula or not formula.strip():
        return (formula, 'high', '')

    try:
        tokens = tokenize_tableau(formula)
        parser = TableauToDaxParser(tokens, field_table_map)
        translated_str = parser.parse_full()

        has_warnings = any("has no exact DAX translation" in n for n in parser.notes)

        if has_warnings:
            return (formula, 'low', 'No deterministic rule — send to AI for translation')

        confidence = 'medium' if parser.has_complex_rule else 'high'
        notes_str = "; ".join(parser.notes)
        return (translated_str, confidence, notes_str)

    except Exception as e:
        return (formula, 'low', f'Error during translation: {str(e)}')


def translate_dax_to_tableau(formula, field_table_map):
    """
    Translate a DAX formula to a Tableau formula using deterministic rules.
    
    Parameters:
    - formula (str): The DAX formula.
    - field_table_map (dict): Mapping of {field_name: table_name} to resolve field prefixes.
    
    Returns:
    - (translated_str, confidence, notes)
    """
    if not formula or not formula.strip():
        return (formula, 'high', '')

    try:
        tokens = tokenize_dax(formula)
        parser = DaxToTableauParser(tokens, field_table_map)
        translated_str = parser.parse_full()

        has_warnings = any("has no exact Tableau translation" in n for n in parser.notes)

        if has_warnings:
            return (formula, 'low', 'No deterministic rule — send to AI for translation')

        confidence = 'medium' if parser.has_complex_rule else 'high'
        notes_str = "; ".join(parser.notes)
        return (translated_str, confidence, notes_str)

    except Exception as e:
        return (formula, 'low', f'Error during translation: {str(e)}')
