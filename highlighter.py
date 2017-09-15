
from pygments import lex
from pygments.lexers import Python3Lexer
from pygments.token import Token

token_map = {
    Token.Keyword: {'foreground': 'keyword'}
}


def read_code(file_path):
    with open(file_path, 'r') as f:
        return f.read()


def get_rows(file_path):
    row = []
    for ttype, tcontent in lex(read_code(file_path), Python3Lexer()):
        if ttype is Token.Text and tcontent == '\n':
            yield row
            row = []
        else:
            tstyle = token_map.get(ttype)
            if tstyle:
                token = tstyle.copy()
                token['content'] = tcontent
                row.append(token)
            else:
                row.append(tcontent)
    yield row
