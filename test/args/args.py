import argparse

parser = argparse.ArgumentParser(description='test the args', 
formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('-c',
                    default='all',
                    const='all',
                    nargs='?',
                    choices=['eject', 'sort', 'all'],
                    help='''Define command to execute (default: %(default)s)
    eject: Eject a card into sorter
    sort: Move a cart from the sorter into a basket
''')
parser.add_argument('-n', 
  action='store',
  nargs='?', 
  default=1,
  const=1,
  type=int,
  help='repeat count')
parser.add_argument('-x', 
  action='store',
  nargs='?', 
  default=1,
  const=1,
  type=int,
  help='xyz')
parser.print_help()
args = parser.parse_args()
print(args)
print(args.n)
print(type(args.c))
print(args.c)
print(args.n)
print(args.x)
