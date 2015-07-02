import sys
import numpy as np

from .mc import samplers, engines, observers

def sample_state(state, blocks, stepout=1, slicing=True, N=1, doprint=False):
    eng = engines.SequentialBlockEngine(state)
    opsay = observers.Printer()
    ohist = observers.HistogramObserver(block=blocks[0])
    eng.add_samplers([samplers.SliceSampler(stepout, block=b) for b in blocks])

    eng.add_likelihood_observers(opsay) if doprint else None
    eng.add_state_observers(ohist)

    eng.dosteps(N)
    return ohist

def sample_ll(state, element, size=0.1, N=1000):
    start = state.state[element]

    ll = []
    vals = np.linspace(start-size, start+size, N)
    for val in vals:
        state.update(element, val)
        l = state.loglikelihood()
        ll.append(l)

    state.update(element, start)
    return vals, np.array(ll)

def scan_noise(image, state, element, size=0.01, N=1000):
    start = state.state[element]

    xs, ys = [], []
    for i in xrange(N):
        print i
        test = image + np.random.normal(0, state.sigma, image.shape)
        x,y = sample_ll(test, state, element, size=size, N=300)
        state.update(element, start)
        xs.append(x)
        ys.append(y)

    return xs, ys

def sample_particles(state, stepout=1):
    print '{:-^39}'.format(' POS / RAD ')
    for particle in xrange(state.obj.N):
        if not state.isactive(particle):
            continue

        print particle
        sys.stdout.flush()

        blocks = state.blocks_particle(particle)
        sample_state(state, blocks, stepout=stepout)

    return state.state.copy()

def sample_particle_pos(state, stepout=1):
    print '{:-^39}'.format(' POS ')
    for particle in xrange(state.obj.N):
        if not state.isactive(particle):
            continue

        print particle
        sys.stdout.flush()

        blocks = state.blocks_particle(particle)[:-1]
        sample_state(state, blocks, stepout=stepout)

    return state.state.copy()

def sample_particle_rad(state, stepout=1):
    print '{:-^39}'.format(' POS ')
    for particle in xrange(state.obj.N):
        if not state.isactive(particle):
            continue

        print particle
        sys.stdout.flush()

        blocks = [state.blocks_particle(particle)[-1]]
        sample_state(state, blocks, stepout=stepout)

    return state.state.copy()

def sample_block(state, blockname, explode=True, stepout=0.1):
    print '{:-^39}'.format(' '+blockname.upper()+' ')
    blocks = [state.create_block(blockname)]

    if explode:
        blocks = state.explode(blocks[0])

    return sample_state(state, blocks, stepout)

def feature(rawimage, sweeps=20, samples=10, prad=7.3, psize=9,
        pad=22, imsize=-1, imzstart=0, zscale=1.06, sigma=0.02, invert=False,
        PSF=(2.0, 4.1), ORDER=(3,3,2), threads=-1):

    from cbamf import states, initializers
    from cbamf.comp import objs, psfs, ilms

    burn = sweeps - samples

    print "Initial featuring"
    itrue = initializers.normalize(rawimage[imzstart:,:imsize,:imsize], invert)
    xstart, proc = initializers.local_max_featuring(itrue, psize, psize/3.)
    itrue = initializers.normalize(itrue, True)
    itrue = np.pad(itrue, pad, mode='constant', constant_values=-10)
    xstart += pad
    rstart = prad*np.ones(xstart.shape[0])
    initializers.remove_overlaps(xstart, rstart)

    print "Making state"
    imsize = itrue.shape
    obj = objs.SphereCollectionRealSpace(pos=xstart, rad=rstart, shape=imsize)
    psf = psfs.AnisotropicGaussian(PSF, shape=imsize, threads=threads)
    ilm = ilms.LegendrePoly3D(order=ORDER, shape=imsize)
    s = states.ConfocalImagePython(itrue, obj=obj, psf=psf, ilm=ilm,
            zscale=zscale, pad=pad, sigma=sigma)

    sample_particles(s, stepout=1)
    return do_samples(s, sweeps, burn, stepout=0.05)

def do_samples(s, sweeps, burn, stepout=0.1):
    h = []
    ll = []
    for i in xrange(sweeps):
        print '{:=^79}'.format(' Sweep '+str(i)+' ')

        sample_particles(s, stepout=stepout)
        sample_block(s, 'psf', stepout=stepout)
        sample_block(s, 'ilm', stepout=stepout)
        sample_block(s, 'off', stepout=stepout)
        sample_block(s, 'zscale', stepout=stepout)

        if i >= burn:
            h.append(s.state.copy())
            ll.append(s.loglikelihood())

    h = np.array(h)
    ll = np.array(ll)
    return h, ll

def build_bounds(state):
    bounds = []

    bound_dict = {
        'pos': (1,512),
        'rad': (0, 20),
        'typ': (0,1),
        'psf': (0, 10),
        'bkg': (-100, 100),
        'amp': (-3, 3),
        'zscale': (0.5, 1.5)
    }

    for i,p in enumerate(state.param_order):
        bounds.extend([bound_dict[p]]*state.param_lengths[i])
    return np.array(bounds)

def loglikelihood(vec, state):
    state.set_state(vec)
    state.create_final_image()
    return -state.loglikelihood()

def gradloglikelihood(vec, state):
    state.set_state(vec)
    return -state.gradloglikelihood()

def gradient_descent(state, method='L-BFGS-B'):
    from scipy.optimize import minimize

    bounds = build_bounds(state)
    minimize(loglikelihood, state.state, args=(state,),
            method=method, jac=gradloglikelihood, bounds=bounds)

def gd(state, N=1, ratio=1e-1):
    state.set_current_particle()
    for i in xrange(N):
        print state.loglikelihood()
        grad = state.gradloglikelihood()
        n = state.state + 1.0/np.abs(grad).max() * ratio * grad
        state.set_state(n)
        print state.loglikelihood()
