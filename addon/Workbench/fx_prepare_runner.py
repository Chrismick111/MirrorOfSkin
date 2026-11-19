"""Short-lived isolated interpreter for FXP2 preparation."""
import pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import fx_activation

def main():
    if len(sys.argv)!=3:return 2
    root=pathlib.Path(sys.argv[1]);game=pathlib.Path(sys.argv[2])
    return 0 if fx_activation.prepare_start(root,game,lambda s:print(s,flush=True)) else 3

if __name__=='__main__':sys.exit(main())
