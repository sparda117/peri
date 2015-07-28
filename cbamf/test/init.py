import numpy as np
import scipy as sp

from cbamf.comp import psfs, ilms, objs
from cbamf.test import poissondisks
from cbamf import states

def _seed_or_not(seed=None):
    if seed is None:
        np.random.seed()
    else:
        np.random.seed(seed)

def _toarr(i):
    if not hasattr(i, '__iter__'):
        i = np.array((i,)*3)
    return i

#=======================================================================
# Generating fake data
#=======================================================================
def create_state(image, pos, rad, sigma=0.05, psftype='gaussian_anisotropic',
        ilmtype='polynomial', psfargs=(2.0, 4.0), ilmorder=(1,1,1), stateargs={}):
    """
    Create a state from a blank image, set of pos and radii

    Parameters:
    -----------
    image : blank image of already padded
    pos : padded positions
    rad : radii array
    sigma : float, noise level

    psftype : ['gaussian_anisotropic', 'gaussian_pca']
        which type of psf to use in the state

    ilmtype : ['polynomial', 'legendre']
        which type of illumination field

    psfargs : arguments to the psf object
    ilmorder : the order of the polynomial for illumination field
    stateargs : dictionary of arguments to pass to state
    """
    tpsfs = ['gaussian_anisotropic', 'gaussian_pca']
    tilms = ['polynomial', 'legendre']

    obj = objs.SphereCollectionRealSpace(pos=pos, rad=rad, shape=image.shape)
    psf = psfs.AnisotropicGaussian(psfargs, shape=image.shape)

    if ilmtype == 'polynomial':
        ilm = ilms.Polynomial3D(order=ilmorder, shape=image.shape)
    if ilmtype == 'legendre':
        ilm = ilms.LegendrePoly3D(order=ilmorder, shape=image.shape)

    s = states.ConfocalImagePython(image, obj=obj, psf=psf, ilm=ilm, sigma=sigma, **stateargs)
    s.model_to_true_image()
    return s 

def create_state_random_packing(imsize, radius=5.0, phi=0.5, seed=None, *args, **kwargs):
    """
    Creates a random packing of spheres and generates the state

    Parameters:
    -----------
    imsize : tuple, array_like, or integer
        the unpadded image size to fill with particles

    radius : float
        radius of particles to add

    seed : integer
        set the seed if desired

    *args, **kwargs : see create_state
    """
    _seed_or_not(seed)
    imsize = _toarr(imsize)

    blank = np.zeros(imsize, dtype='float')
    disks = poissondisks.DiskCollection(imsize-radius, 2*radius)
    xstart = disks.get_positions() + radius/4
    image, pos, rad = states.prepare_for_state(blank, xstart, radius)
    
    return create_state(image, pos, rad, *args, **kwargs)

def create_single_particle_state(imsize, radius=5.0, seed=None, *args, **kwargs):
    """
    Creates a single particle state

    Parameters:
    -----------
    imsize : tuple, array_like, or integer
        the unpadded image size to fill with particles

    radius : float
        radius of particles to add

    seed : integer
        set the seed if desired

    *args, **kwargs : see create_state
    """
    _seed_or_not(seed)
    imsize = _toarr(imsize)

    image, pos, rad = states.prepare_for_state(np.zeros(imsize),
            imsize.reshape(-1,3)/2.0, radius)

    return create_state(image, pos, rad, *args, **kwargs)

def create_two_particle_state(imsize, radius=5.0, delta=1.0, seed=None, *args, **kwargs):
    """
    Creates a two particle state

    Parameters:
    -----------
    imsize : tuple, array_like, or integer
        the unpadded image size to fill with particles

    radius : float
        radius of particles to add

    delta : float
        separation between the two particles

    seed : integer
        set the seed if desired

    *args, **kwargs : see create_state
    """
    _seed_or_not(seed)
    imsize = _toarr(imsize)

    d = np.array([0.0, 0.0, float(radius)+float(delta)/2])
    pos = np.array([imsize/2 - d, imsize/2 + d]).reshape(-1,3)
    rad = np.array([radius, radius])

    image, pos, rad = states.prepare_for_state(np.zeros(imsize), pos, rad)
    return create_state(image, pos, rad, *args, **kwargs)
