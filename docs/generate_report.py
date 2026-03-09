import os, json, subprocess, datetime

def get_cycle():
    # read identity.md for latest cycle number
    with open('memory/identity.md','r') as f:
        for line in f:
            if 'Cycle' in line and 'Evolution Cycle' in line:
                # format: Evolution Cycle 106
                parts=line.split()
                try:
                    return int(parts[-1])
                except:
                    continue
    return None

def get_metrics():
    # simple git diff stats for last commit
    result=subprocess.check_output(['git','log','-1','--pretty=%B']).decode()
    # placeholder metrics
    lines_changed=0
    try:
        diff=subprocess.check_output(['git','diff','HEAD~1','HEAD','--shortstat']).decode()
        if diff:
            parts=diff.split(',')
            for p in parts:
                if 'files changed' in p:
                    continue
                if 'insertions' in p:
                    lines_changed=int(p.strip().split()[0])
    except Exception:
        pass
    return {'lines_changed':lines_changed}

def main():
    cycle=get_cycle()
    metrics=get_metrics()
    template_path='docs/report_template.md'
    with open(template_path,'r') as f:
        tmpl=f.read()
    report=tmpl.replace('{{CYCLE}}',str(cycle))
    report=report.replace('{{LINES_CHANGED}}',str(metrics['lines_changed']))
    # add self‑question placeholder
    report=report.replace('{{SELF_QUESTION}}','What new capability should I explore next?')
    out_path=f'docs/evolution_report_cycle_{cycle}.md'
    with open(out_path,'w') as f:
        f.write(report)
    print('Report generated',out_path)

if __name__=='__main__':
    main()
