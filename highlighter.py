
from cui.util import intersperse

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
        # Handle multiline tokens
        splitted_content = intersperse(
            [(Token.Literal.String.Doc, tcontent)
             for tcontent in tcontent.split('\n')] \
            if ttype is Token.Literal.String.Doc else \
            [(ttype, tcontent)],
            (Token.Text, '\n')
        )

        # Yield tokens
        for ttype, tcontent in splitted_content:
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


class SourceManager(object):
    def __init__(self):
        self._sources = {}

    def get_file(self, file_path):
        if file_path not in self._sources:
            self._sources[file_path] = list(get_rows(file_path))
        return self._sources[file_path]
