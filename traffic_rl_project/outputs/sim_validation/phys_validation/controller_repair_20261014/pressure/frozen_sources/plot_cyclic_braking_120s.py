from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
src=Path(r'D:\Codex\Documents\Train\controller_extended_20261014\overlap_release_first_after_01')
out=Path(r'D:\Codex\Documents\Train\controller_pressure_20261014\cyclic_braking_120s_20261014.png')
d=np.load(src/'trajectory.npz'); meta=json.loads((src/'result.json').read_text(encoding='utf-8')); t=d['rows'][:,0]
fig,axs=plt.subplots(4,1,figsize=(12,12),sharex=True)
colors=['#2274a5','#e1812c','#37965c']
for i,c in enumerate(colors):
    axs[0].plot(t,d['rows'][:,i+1]*3.6,color=c,label=f'Train {i+1} mean')
    axs[0].plot(t,d['max_vehicle_speed'][:,i]*3.6,color=c,ls=':',alpha=.55)
    states=np.array([{'RELEASE':0,'HOLD':1,'SERVICE':2,'EMERGENCY':3}[str(v)] for v in d['ab_command_to_physics'][:,i]])
    axs[1].step(t,states+i*.045,where='post',color=c,label=f'Train {i+1}')
    for j,ls in enumerate(['-','--']):
        axs[2].plot(t,d['physical_loco_ed'][:,i,j],color=c,ls=ls,alpha=.8,label=f'Train {i+1} '+('front' if j==0 else 'middle'))
    f=np.max(np.abs(d['coupler_interface_force_n'][:,i,:]),axis=1)/1000
    axs[3].plot(t,f,color=c,label=f'Train {i+1}')
axs[0].axhline(80,color='#b52b35',ls='--',label='80 km/h limit')
axs[0].set_ylabel('Speed (km/h)'); axs[0].legend(ncol=4,fontsize=9)
axs[1].set_yticks([0,1,2,3],['Release','Hold','Service','Emergency']); axs[1].set_ylabel('Actual air command'); axs[1].legend(ncol=3,fontsize=9)
axs[2].set_ylabel('Actual ED fraction'); axs[2].set_ylim(-.05,1.08); axs[2].legend(ncol=3,fontsize=8)
axs[3].set_ylabel('Peak |coupler force| (kN)'); axs[3].axhline(1000,color='#b52b35',ls='--',label='1000 kN limit'); axs[3].legend(ncol=4,fontsize=9)
axs[-1].set_xlabel('Simulation time (s)')
for ax in axs: ax.grid(alpha=.22); ax.set_xlim(t[0],t[-1])
fig.suptitle('Cyclic braking process: archived 120-second segment\n3 trains | 21,976 t each | 1 loco + 108 wagons + 1 loco + 108 wagons | initial 65 km/h',fontsize=12)
fig.text(.5,.012,'Actual route profile: Shuozhou-Ningwuxi-Beidaniu 49.6 km; leader starts at 16 km.\nArchived before episode-reset repair; zero RL modulation. Dotted speed curves: vehicle maxima.',ha='center',fontsize=9)
fig.tight_layout(rect=[0,.05,1,.94]); fig.savefig(out,dpi=170); plt.close(fig)
print(str(out))
print('peak_kN',meta['summary']['peak_kn'],'max_vehicle_kmh',meta['summary']['max_vehicle_speed_kmh'])
