import pydevd
import runpy
import sys

def main():
    debug_host = sys.argv.pop(1)
    debug_port = int(sys.argv.pop(1))
    bin_module = sys.argv.pop(1)

    pydevd.settrace(debug_host,
                    port=debug_port,
                    stdoutToServer=True,
                    stderrToServer=True,
                    suspend=False)

    runpy.run_path(bin_module, run_name='__main__')


if __name__ == '__main__':
    if sys.argv < 4:
        print "Usage: prog debug_host debug_port module [ args ... ]"

    main()
