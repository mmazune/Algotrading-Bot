import json
WEIGHTS_C = {"C1":15,"C2":15,"C3":10,"C4":10,"C5":15,"C6":15,"C7":20}
WEIGHTS_D = {"D1":15,"D2":15,"D3":20,"D4":15,"D5":20,"D6":15}
def main():
    with open("progress.json","r") as f:
        P = json.load(f)
    def score(section, weights):
        total=0.0; got=0.0
        for key,w in weights.items():
            total += w
            checks = P[section]["checks"].get(key, [])
            if not checks: continue
            done = (sum(1 for x in checks if x)/len(checks))
            got += w*done
        return (got, total)
    cgot, ctot = score("coding", WEIGHTS_C)
    dgot, dtot = score("deployment", WEIGHTS_D)
    cperc = (cgot/ctot)*100; dperc = (dgot/dtot)*100
    proj = (cperc + dperc)/2.0
    print(f"Coding: {cperc:.1f}%   Deployment: {dperc:.1f}%   Project Total: {proj:.1f}%")
if __name__ == "__main__":
    main()
