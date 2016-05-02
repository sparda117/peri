import os
import sys
import pickle
import numpy as np
import trackpy as tp
from pandas import DataFrame

def track(pos, rad, maxdisp=2., threshold=None):
    """
    Accepts positions and radii as a list of frames in the shape [N, D] where
    N in the number of particles (can vary by frame) and D the number of
    dimensions.
    """
    threshold = threshold or len(pos)
    z,y,x,a,f = [],[],[],[],[]

    for i,(p,r) in enumerate(zip(pos, rad)):
        z.extend(p[:,0].tolist())
        y.extend(p[:,1].tolist())
        x.extend(p[:,2].tolist())
        a.extend(r.tolist())
        f.extend([i]*r.shape[0])

    df = DataFrame({'x': x, 'y': y, 'z': z, 'rad': a,'frame': f})
    linked = tp.filter_stubs(
        tp.link_df(df, maxdisp, pos_columns=['x','y','z']),
        threshold=threshold
    )
    return linked

def get_xyzr_t(df, particle_ind):
    
    ind = df['particle'] == particle_ind
    
    rads = np.array(df['rad'][ind].copy())
    z = np.array(df['z'][ind].copy())
    x = np.array(df['x'][ind].copy())
    y = np.array(df['y'][ind].copy())
    
    return x,y,z,rads
    
def msd(df, maxlag, pxsize=0.126, scantime=0.1):
    drift = tp.compute_drift(df)
    tm = tp.subtract_drift(df, drift)
    em = tp.emsd(tm, pxsize, scantime, max_lagtime=maxlag, pos_columns=['x','y','z'])
    return em

"""    
df = make_big_df()
linked = tp.filter_stubs( tp.link_df( df, 6, pos_columns = ['x','y','z'] ), 30 )
    
r_moments = []
for a in xrange( int( df['particle'].max() ) ):
    x,y,z,r = get_xyzr_t(df, 1*a )
    if x.size > 1:
        r_moments.append( [x.mean(), y.mean(), z.mean(), r.mean(),r.std()] )
        
#Just fucking around now:
drift = tp.compute_drift(linked)
tm = tp.subtract_drift( linked, drift )
em = tp.emsd( tm, 1.0, 1.0, max_lagtime = 10, pos_columns = ['x','y','z'] )
"""
