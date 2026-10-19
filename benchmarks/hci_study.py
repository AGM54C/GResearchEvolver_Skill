"""Repository entry point for the installed runtime's HCI pilot preparation/analysis."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'))
from gresearch.study import main
if __name__=='__main__':main()
