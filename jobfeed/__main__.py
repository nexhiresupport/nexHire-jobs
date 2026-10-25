"""Entry point: python -m jobfeed  (or  python __main__.py)"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from jobfeed.runner import main
main()
