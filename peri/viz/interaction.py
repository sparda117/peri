from builtins import range, object

import numpy as np
import matplotlib as mpl
import matplotlib.pylab as pl
from matplotlib.gridspec import GridSpec

import peri.opt.optimize as opt
from peri.util import Tile

from peri.logger import log
log = log.getChild('interaction')


class OrthoGridAxes(object):
    def __init__(self, field, vmin=None, vmax=None, cmap='bone', scale=10,
                 dohist=False, linewidth=1, linecolor='y', linestyle='dashed',
                 tooltips=None):
        """
        A set of 3 axes to show a 3D image orthogonally

        Parameters
        ----------
        field : np.ndarray
            The (real, 3D) array to view.
        """
        self.vmin = field.min() if vmin is None else vmin
        self.vmax = field.max() if vmax is None else vmax
        self.field = field
        self.cmap = cmap
        self.dohist = dohist
        self.linewidth = linewidth
        self.linecolor = linecolor
        self.linestyle = linestyle

        z, y, x = [float(i) for i in self.field.shape]
        w = x + z
        h = y + z

        tooltip = mpl.rcParams['toolbar']
        if not tooltips:
            mpl.rcParams['toolbar'] = 'None'
        self.fig = pl.figure(figsize=(scale *w / h, scale))
        mpl.rcParams['toolbar'] = tooltip

        # add_axes takes a rectange = left, bottom,width, height
        self.grid_axes = {
            'xy': self.fig.add_axes((0.0, 1-y/h, x/w,   y/h)),
            'yz': self.fig.add_axes((0.0, 0.0,   x/w,   1-y/h)),
            'xz': self.fig.add_axes((x/w, 1-y/h, 1-x/w, y/h)),
            'in': self.fig.add_axes((x/w, 0.0,   1-x/w, 1-y/h)),
        }

        # Draw at the center of the initial image:
        self.draw_ortho(np.array(self.field.shape)/2)
        if self.dohist:
            self.update_hist()
        self._format_ax(self.grid_axes['in'])

    def update_field(self, new_field):
        """Updates the values in the field to draw"""
        if new_field.shape != self.field.shape:
            raise ValueError('new field must be same shape as old')
        self.field = new_field
        if self.dohist:
            self.update_hist()

    def draw_ortho(self, center_point):
        """Draws the ortho projection of at the current slices"""
        im, vmin, vmax, cmap = self.field, self.vmin, self.vmax, self.cmap

        int_center = np.round(np.clip(center_point, 0, np.array(
            self.field.shape))).astype('int')

        for ax in self.grid_axes.values():
            ax.cla()
        imshow_kwargs = {'vmin':self.vmin, 'vmax':self.vmax, 'cmap':self.cmap}
        line_kwargs = {'colors':self.linecolor, 'linestyles':self.linestyle,
                       'lw':self.linewidth}

        # 1. xy
        self.grid_axes['xy'].imshow(im[int_center[0],:,:], **imshow_kwargs)
        self.grid_axes['xy'].hlines(center_point[1], 0, im.shape[2],
                                    **line_kwargs)
        self.grid_axes['xy'].vlines(center_point[2], 0, im.shape[1],
                                    **line_kwargs)
        self._format_ax(self.grid_axes['xy'])

        # 2. yz
        self.grid_axes['yz'].imshow(im[:,int_center[1],:], **imshow_kwargs)
        self.grid_axes['yz'].hlines(center_point[0], 0, im.shape[2],
                **line_kwargs)
        self.grid_axes['yz'].vlines(center_point[2], 0, im.shape[0],
                **line_kwargs)
        self._format_ax(self.grid_axes['yz'])

        # 3. xz
        self.grid_axes['xz'].imshow(im[:,:,int_center[2]].T, **imshow_kwargs)
        self.grid_axes['xz'].hlines(center_point[1], 0, im.shape[0],
                **line_kwargs)
        self.grid_axes['xz'].vlines(center_point[0], 0, im.shape[1],
                **line_kwargs)
        self._format_ax(self.grid_axes['xz'])

        pl.draw()

    def update_hist(self):
        """Draws and calculates the histogram of the field"""
        tt = np.real(self.field).ravel()
        c, s = tt.mean(), 5*tt.std()
        y, x = np.histogram(tt, bins=np.linspace(c-s, c+s, 700), normed=True)
        x = (x[1:] + x[:-1])/2

        ax = self.grid_axes['in']
        ax.cla()

        ax.plot(x, y, 'k-', lw=1)
        ax.fill_between(x, y, 1e-10, alpha=0.5)
        ax.set_yscale('log', nonposy='clip')

        ax.set_xlim(c-s, c+s)
        ax.set_ylim(1e-3*y.max(), 1.4*y.max())

        self._format_ax(ax)
        pl.draw()

    def _format_ax(self, ax):
        ax.set_xticks([])
        ax.set_yticks([])

class OrthoManipulator(object):
    def __init__(self, state, size=8, cmap_abs='bone', cmap_diff='RdBu',
            incsize=18.0, orientation=None, vrange_img=1.0, vrange_diff=0.1):
        """
        An interactive viewer for states for a model in 3D. Can work with
        any 3D state with a set of components. This viewer relies heavily on
        hotkeys. The various modes that can be accessed are by pressing
        these keys:

            'Q' : switch between 'model', 'residual', and 'component' views
            'A' : add particle mode (click position to add)
            'R' : remove particle mode (click position to remove)
            'E' : optimize particle (click particle to optimize)
            'W' : switch to fourier views
            'V' : switch to view mode (click window to move view)
            'C' : If in 'component' views, cycles through components

        Parameters:
        -----------
        state : `peri.states.State` object
            The state object to look at

        size : float
            Relative window size, this is based on matplotlib.figure(figsize)
            and has some units which I don't understand.

        cmap_abs : string
            Colormap to use for the one sided scales such as data and model

        cmap_dff : string
            Colormap to use for difference images, such as residuals

        orientation : one of ['h', 'v', 'horizontal', 'vertical']
            The orientation of the two views

        vrange_img : float
            vmax for imshow for absolute images

        vrange_diff : float
            vmax - vmin for imshow for difference images
        """
        self.incsize = incsize
        self.modes = ['view', 'add', 'remove', 'grab', 'optimize']
        self.mode = self.modes[0]

        self.insets = ['exposure']
        self.inset = 'none'

        self.views = ['field', 'diff', 'comp']
        self.view = self.views[0]

        self.modifiers = ['none', 'fft']
        self.modifier = self.modifiers[0]

        self.components = [
            c.category for c in state.comps if isinstance(c.get(), np.ndarray)
        ]
        self.component = self.components[0]

        self.state = state
        self.cmap_abs = cmap_abs
        self.cmap_diff = cmap_diff
        self.vrange_img = vrange_img
        self.vrange_diff = vrange_diff

        self.state.set_tile(self.state.oshape)

        z,y,x = [float(i) for i in self.state.data.shape]
        w = float(x + z)
        h = float(y + z)

        #tooltip = mpl.rcParams['toolbar']
        #mpl.rcParams['toolbar'] = 'None'

        orientation = orientation or ('horizontal' if w/h < 1.4 else 'vertical')
        if orientation == 'horizontal' or orientation == 'h':
            self.fig = pl.figure(figsize=(2*size*w/h,size))
            Sx, Sy, xoff, yoff = 0.5, 1.0, 0.5, 0.0
        elif orientation == 'vertical' or orientation == 'v':
            self.fig = pl.figure(figsize=(size,2*size*h/w))
            Sx, Sy, xoff, yoff = 1.0, 0.5, 0.0, 0.5
        else:
            raise AttributeError("orientation must be one of '(h)orizontal', '(v)ertical'")

        #mpl.rcParams['toolbar'] = tooltip

        self.gl = {}
        # rect = l,b,w,h
        self.gl['xy'] = self.fig.add_axes((Sx*0.0, yoff+Sy*(1-y/h), Sx*x/w,     Sy*y/h))
        self.gl['yz'] = self.fig.add_axes((Sx*0.0, yoff+Sy*0.0,     Sx*x/w,     Sy*(1-y/h)))
        self.gl['xz'] = self.fig.add_axes((Sx*x/w, yoff+Sy*(1-y/h), Sx*(1-x/w), Sy*y/h))
        self.gl['in'] = self.fig.add_axes((Sx*x/w, yoff+Sy*0.0,     Sx*(1-x/w), Sy*(1-y/h)))

        self.gr = {}
        self.gr['xy'] = self.fig.add_axes((xoff+Sx*0.0, Sy*(1-y/h), Sx*x/w,     Sy*y/h))
        self.gr['yz'] = self.fig.add_axes((xoff+Sx*0.0, Sy*0.0,     Sx*x/w,     Sy*(1-y/h)))
        self.gr['xz'] = self.fig.add_axes((xoff+Sx*x/w, Sy*(1-y/h), Sx*(1-x/w), Sy*y/h))
        self.gr['in'] = self.fig.add_axes((xoff+Sx*x/w, Sy*0.0,     Sx*(1-x/w), Sy*(1-y/h)))

        self.slices = (np.array(self.state.data.shape)/2).astype('int')

        self._grab = None
        self.set_field()
        self.draw()
        self.register_events()

    def _format_ax(self, ax):
        ax.set_xticks([])
        ax.set_yticks([])

    def set_field(self):
        if self.view == 'field':
            out = self.state.model
            vmin, vmax = 0.0, self.vrange_img
            cmap = self.cmap_abs

        if self.view == 'diff':
            out = (self.state.data - self.state.model)
            vmin, vmax = -self.vrange_diff, self.vrange_diff
            cmap = self.cmap_diff

        if self.view == 'comp':
            out = self.state.get(self.component).get()[self.state.inner]
            vmin, vmax = 0.0, self.vrange_img
            cmap = self.cmap_abs

        if self.modifier == 'fft':
            out = np.real(np.abs(np.fft.fftn(out)))**0.2
            out[0,0,0] = 1.0
            out = np.fft.fftshift(out)
            vmin = out.min()
            vmax = out.max()
            cmap = self.cmap_abs

        self.field = out
        self.vmin = vmin
        self.vmax = vmax
        self.cmap = cmap

    def draw(self):
        self.draw_ortho(self.state.data, self.gl, cmap=self.cmap_abs, vmin=0.0, vmax=self.vrange_img)
        self.draw_ortho(self.field, self.gr, cmap=self.cmap, vmin=self.vmin, vmax=self.vmax)

    def draw_ortho(self, im, g, cmap=None, vmin=0, vmax=1):
        slices = self.slices
        int_slice = np.clip(np.round(slices), 0, np.array(im.shape)-1).astype('int')

        g['xy'].cla()
        g['yz'].cla()
        g['xz'].cla()
        g['in'].cla()

        g['xy'].imshow(im[int_slice[0],:,:], vmin=vmin, vmax=vmax, cmap=cmap)
        g['xy'].hlines(slices[1], 0, im.shape[2], colors='y', linestyles='dashed', lw=1)
        g['xy'].vlines(slices[2], 0, im.shape[1], colors='y', linestyles='dashed', lw=1)
        self._format_ax(g['xy'])

        g['yz'].imshow(im[:,int_slice[1],:], vmin=vmin, vmax=vmax, cmap=cmap)
        g['yz'].hlines(slices[0], 0, im.shape[2], colors='y', linestyles='dashed', lw=1)
        g['yz'].vlines(slices[2], 0, im.shape[0], colors='y', linestyles='dashed', lw=1)
        self._format_ax(g['yz'])

        g['xz'].imshow(im[:,:,int_slice[2]].T, vmin=vmin, vmax=vmax, cmap=cmap)
        g['xz'].hlines(slices[1], 0, im.shape[0], colors='y', linestyles='dashed', lw=1)
        g['xz'].vlines(slices[0], 0, im.shape[1], colors='y', linestyles='dashed', lw=1)
        self._format_ax(g['xz'])

        if self.inset == 'exposure':
            m = im*self.state.image_mask
            self.pix = np.r_[m[slices[0],:,:], m[:,:,slices[2]], m[:,slices[1],:]].ravel()
            self.pix = self.pix[self.pix != 0.]
            g['in'].hist(self.pix, bins=300, histtype='step')
            g['in'].semilogy()

            g['in'].set_xlim(0, 1)
            g['in'].set_ylim(9e-1, 1e3)

            if self.view == 'diff' and g == self.gr:
                g['in'].set_xlim(-0.3, 0.3)

        self._format_ax(g['in'])
        pl.draw()

    def register_events(self):
        self._calls = []

        self._calls.append(self.fig.canvas.mpl_connect('key_press_event', self.key_press_event))

        if self.mode == 'view':
            self._calls.append(self.fig.canvas.mpl_connect('button_press_event', self.mouse_press_view))
        if self.mode == 'add':
            self._calls.append(self.fig.canvas.mpl_connect('button_press_event', self.mouse_press_add))
        if self.mode == 'remove':
            self._calls.append(self.fig.canvas.mpl_connect('button_press_event', self.mouse_press_remove))
        if self.mode == 'optimize':
            self._calls.append(self.fig.canvas.mpl_connect('button_press_event', self.mouse_press_optimize))
        if self.mode == 'grab':
            self._calls.append(self.fig.canvas.mpl_connect('button_press_event', self.mouse_press_grab))
            self._calls.append(self.fig.canvas.mpl_connect('motion_notify_event', self.mouse_move_grab))
            self._calls.append(self.fig.canvas.mpl_connect('button_release_event', self.mouse_release_grab))
            self._calls.append(self.fig.canvas.mpl_connect('scroll_event', self.mouse_scroll_grab))

    def mouse_press_grab(self, event):
        self.event = event
        p = self._pt_xyz(event)

        if p is not None:
            self._grab = self.state.obj_closest_particle(p)

            param = self.state.param_particle_pos(self._grab)
            self._pos = self.state.get_values(param)
        else:
            self._grab = None

    def mouse_release_grab(self, event):
        self.event = event
        self._grab = None

    def mouse_move_grab(self, event):
        self.event = event
        p = self._pt_xyz(event)

        if p is not None and self._grab is not None:
            b = self.state.param_particle_pos(self._grab)
            self.state.update(b, p)
            self.set_field()
            self.draw()

    def mouse_scroll_grab(self, event):
        self.event = event
        p = self._pt_xyz(event)

        if p is not None:
            n = self.state.obj_closest_particle(p)
            b = self.state.param_particle_rad(n)
            self.state.update(b, np.array(self.state.get_values(b))+event.step/self.incsize)
            self.set_field()
            self.draw()

    def _pt_xyz(self, event):
        x0 = event.xdata
        y0 = event.ydata

        f = False
        for g in [self.gl, self.gr]:
            if event.inaxes == g['xy']:
                x = x0
                y = y0
                z = self.slices[0]
                f = True
            if event.inaxes == g['yz']:
                x = x0
                y = self.slices[1]
                z = y0
                f = True
            if event.inaxes == g['xz']:
                x = self.slices[2]
                y = y0
                z = x0
                f = True

        if f:
            return np.array((z,y,x))
        return None

    def mouse_press_view(self, event):
        self.event = event

        p = self._pt_xyz(event)
        if p is not None:
            log.info("Moving view to [{:.5}, {:.5}, {:.5}]".format(*p))
            self.slices = p
        self.draw()

    def mouse_press_add(self, event):
        self.event = event

        p = self._pt_xyz(event)
        if p is not None:
            p = np.array(p)

            r = self.state.obj_get_radii()
            if len(r) == 0:
                r = 5.0
            else:
                r = r.mean()

            log.info("Adding particle at [{:.5}, {:.5}, {:.5}], {:.4}".format(
                    *(p.tolist() + [r])))
            self.state.obj_add_particle(p, r)
        self.state.set_tile(self.state.oshape)
        self.set_field()
        self.draw()

    def mouse_press_remove(self, event):
        self.event = event

        p = self._pt_xyz(event)
        if p is not None:
            log.info("Removing particle near [{:.5}, {:.5}, {:.5}]".format(*p))
            ind = self.state.obj_closest_particle(p)
            self.state.obj_remove_particle(ind)
        self.state.set_tile(self.state.oshape)
        self.set_field()
        self.draw()

    def mouse_press_optimize(self, event):
        self.event = event
        p = self._pt_xyz(event)

        if p is not None:
            log.info("Optimizing particle near [{:.5}, {:.5}, {:.5}]".format(*p))
            n = self.state.obj_closest_particle(p)
            old_err = self.state.error
            _ = opt.do_levmarq_particles(self.state, np.array([n]), max_iter=2)
            new_err = self.state.error
            log.info('{}->{}'.format(old_err, new_err))

        self.state.set_tile(self.state.oshape)
        self.set_field()
        self.draw()

    def cycle(self, c, clist):
        return clist[(clist.index(c)+1) % len(clist)]

    def key_press_event(self, event):
        self.event = event

        if event.key == 'c':
            self.component = self.cycle(self.component, self.components)
            self.set_field()
            self.draw()
            return
        if event.key == 'v':
            self.mode = 'view'
        if event.key == 'a':
            self.mode = 'add'
        if event.key == 'r':
            self.mode = 'remove'
        if event.key == 'g':
            self.mode = 'grab'
        if event.key == 'e':
            self.mode = 'optimize'
        if event.key == 'q':
            self.view = self.cycle(self.view, self.views)
            self.set_field()
            self.draw()
            return
        if event.key == 'w':
            self.modifier = self.cycle(self.modifier, self.modifiers)
            self.set_field()
            self.draw()
            return

        log.info("Switching mode to {}".format(self.mode))

        for c in self._calls:
            self.fig.canvas.mpl_disconnect(c)

        self.register_events()

#=============================================================================
# A simpler version for a single 3D field viewer
#=============================================================================
class OrthoViewer(object):
    def __init__(self, field, onesided=True, vmin=None, vmax=None, cmap='bone',
                 dohist=False, fourier=False, tooltips=False):
        """
        Easy interactive viewing of 3D ndarray with view selection. Navigate in
        3D by clicking on the three panels which are slices through the array
        at a given position.
        """
        if cmap is not None:
            self.cmap = cmap
        else:
            self.cmap = 'bone' if self.onesided else 'RdBu_r'
        self.fourier = fourier
        if self.fourier:
            self.field = np.fft.fftshift(np.fft.fftn(self.field))
            gafield = np.abs(self.field)
        else:
            gafield = field

        self.grid_axes = OrthoGridAxes(
            gafield, vmin=vmin, vmax=vmax, cmap=self.cmap, dohist=dohist,
            tooltips=tooltips)
        self.slices = np.array(field.shape) * 0.5  # initial view
        self.draw()
        self.register_events()

    def draw(self):
        self.grid_axes.draw_ortho(self.slices)

    def register_events(self):
        self._calls = []
        self._calls.append(self.grid_axes.fig.canvas.mpl_connect(
            'button_press_event', self.mouse_press_view))

    def _pt_xyz(self, event):
        """Translates a click to an x, y, z position in the axes"""
        x0 = event.xdata
        y0 = event.ydata

        f = False
        if event.inaxes == self.grid_axes.grid_axes['xy']:
            x = x0
            y = y0
            z = self.slices[0]
            f = True
        if event.inaxes == self.grid_axes.grid_axes['yz']:
            x = x0
            y = self.slices[1]
            z = y0
            f = True
        if event.inaxes == self.grid_axes.grid_axes['xz']:
            x = self.slices[2]
            y = y0
            z = x0
            f = True

        return np.array((z,y,x)) if f else None

    def mouse_press_view(self, event):
        self.event = event

        p = self._pt_xyz(event)
        if p is not None:
            self.slices = p
        self.draw()

class OrthoPrefeature(OrthoViewer):
    def __init__(self, image, pos, viewrad=None, cmap='Greys_r', part_col=
                [0., 1., 1., 1.], **kwargs):
        """
        Interactive viewing of a 3D featured image, to examine the quality of
        initial featuring.

        There are 3 modes of the viewer, accessed by pressing these keys:
         * 'V' : switch to view mode (click window to move view)
         * 'A' : add particle mode (click position to add)
         * 'R' : remove particle mode (click position to remove)
        The viewer starts in view mode.
        The complete list of particle positions is stored in ``self.pos``

        Parameters
        ----------
        im : numpy.ndarray
            The image to check pre-featuring on.
        pos : [N,3] numpy.ndarray
            The initial guess for the particle positions, in pixel units
        viewrad : Float or None, optional.
            The width of the particles to plot. Default is 2.
        cmap : String, optional
            A valid matplotlib colormap. Default is `'Greys_r'`.s
        part_col : list-like, optional
            Color of the particles.... RGBA. Default is cyan.
        **kwargs : All keyword args to OrthoViewer....
        """
        #Possible to modify this to include varying radii
        self.image = image.copy()
        self.pos = pos
        if viewrad is None:
            self.viewrad = 2.
        else:
            self.viewrad = viewrad
        self.mode = 'view'
        super(OrthoPrefeature, self).__init__(image, cmap=cmap, **kwargs)
        if self.vmin is None:
            self.vmin = image.min()
        if self.vmax is None:
            self.vmax = image.max()

        if type(self.cmap) == str:
            self._cmap = mpl.cm.get_cmap(self.cmap)
        else:  #better be a cmap function
            self._cmap = self.cmap
        self.particle_field = np.zeros(image.shape, dtype='float')
        self.part_col = part_col

        self._draw_im()
        self.update_particle_field(poses=None)
        self.update_field()
        self.draw()

    def _draw_im(self):
        rscl = np.clip((self.image - self.vmin) / (self.vmax - self.vmin), 0,1)
        self._image = self._cmap(rscl)

    def _particle_func(self, coords, pos, wid):
        """Draws a gaussian, range is (0,1]. Coords = [3,n]"""
        dx, dy, dz = [c - p for c,p in zip(coords, pos)]
        dr2 = dx*dx + dy*dy + dz*dz
        return np.exp(-dr2/(2*wid*wid))

    def update_particle_field(self, poses=None, add=True):
        if poses is None:
            poses = self.pos
        wid = self.viewrad
        for p in poses:
            #1. get tile
            l = np.clip(p-2*wid, 0, self.image.shape)
            r = np.clip(p+2*wid, 0, self.image.shape)
            t = Tile(l, r, mins=0, maxs=self.image.shape)
            #2. update:
            c = t.coords(form='broadcast')
            if add:
                self.particle_field[t.slicer] += self._particle_func(c, p, wid)
            else:
                self.particle_field[t.slicer] -= self._particle_func(c, p, wid)

    def update_field(self, poses=None):
        """updates self.field"""
        m = np.clip(self.particle_field, 0, 1)
        part_color = np.zeros(self._image.shape)
        for a in range(4): part_color[:,:,:,a] = self.part_col[a]
        self.field = np.zeros(self._image.shape)
        for a in range(4):
            self.field[:,:,:,a] = m*part_color[:,:,:,a] + (1-m) * self._image[:,:,:,a]

    def draw_ortho(self, im, g, cmap=None, vmin=0, vmax=1):
        im, vmin, vmax, cmap = self.field, self.vmin, self.vmax, self.cmap

        if self.fourier:
            im = np.abs(im)

        slices = self.slices
        int_slice = np.clip(np.round(slices), 0,
                            np.array(im.shape[:3])-1).astype('int')

        # if vmin is None:
            # vmin = im.min()
        # if vmax is None:
            # vmax = im.max()

        # if self.cmap == 'RdBu_r':
            # val = np.max(np.abs([vmin, vmax]))
            # vmin = -val
            # vmax = val

        self.g['xy'].cla()
        self.g['yz'].cla()
        self.g['xz'].cla()
        self.g['in'].cla()

        self.g['xy'].imshow(im[int_slice[0],:,:], cmap=cmap)
        self.g['xy'].hlines(slices[1], 0, im.shape[2], colors='y', linestyles='dashed', lw=1)
        self.g['xy'].vlines(slices[2], 0, im.shape[1], colors='y', linestyles='dashed', lw=1)
        self._format_ax(self.g['xy'])

        self.g['yz'].imshow(im[:,int_slice[1],:], vmin=vmin, vmax=vmax, cmap=cmap)
        self.g['yz'].hlines(slices[0], 0, im.shape[2], colors='y', linestyles='dashed', lw=1)
        self.g['yz'].vlines(slices[2], 0, im.shape[0], colors='y', linestyles='dashed', lw=1)
        self._format_ax(self.g['yz'])

        self.g['xz'].imshow(np.rollaxis(im[:,:,int_slice[2]], 1), cmap=cmap)
        self.g['xz'].hlines(slices[1], 0, im.shape[0], colors='y', linestyles='dashed', lw=1)
        self.g['xz'].vlines(slices[0], 0, im.shape[1], colors='y', linestyles='dashed', lw=1)
        self._format_ax(self.g['xz'])

        if self.dohist:
            tt = np.real(self.field).ravel()
            c, s = tt.mean(), 5*tt.std()
            y,x = np.histogram(tt, bins=np.linspace(c-s, c+s, 700), normed=True)
            x = (x[1:] + x[:-1])/2

            self.g['in'].plot(x, y, 'k-', lw=1)
            self.g['in'].fill_between(x, y, 1e-10, alpha=0.5)
            self.g['in'].set_yscale('log', nonposy='clip')

            self.g['in'].set_xlim(c-s, c+s)
            self.g['in'].set_ylim(1e-3*y.max(), 1.4*y.max())

        self._format_ax(self.g['in'])

        pl.draw()

    def register_events(self):
        self._calls = []
        self._calls.append(self.fig.canvas.mpl_connect('key_press_event',
                self.key_press_event))

        if self.mode == 'view':
            self._calls.append(self.fig.canvas.mpl_connect(
                    'button_press_event', self.mouse_press_view))
        elif self.mode == 'add':
            self._calls.append(self.fig.canvas.mpl_connect(
                    'button_press_event', self.mouse_press_add))
        elif self.mode == 'remove':
            self._calls.append(self.fig.canvas.mpl_connect(
                    'button_press_event', self.mouse_press_remove))

    def key_press_event(self, event):
        self.event = event

        if event.key == 'v':
            self.mode = 'view'
        elif event.key == 'a':
            self.mode = 'add'
        elif event.key == 'r':
            self.mode = 'remove'

        log.info("Switching mode to {}".format(self.mode))

        for c in self._calls:
            self.fig.canvas.mpl_disconnect(c)

        self.register_events()

    def mouse_press_add(self, event):
        self.event = event

        p = self._pt_xyz(event)
        if p is not None:
            p = np.array(p)

            log.info("Adding particle at {}".format(p))
            self.pos = np.append(self.pos, p.reshape((1,-1)), axis=0)
        self.update_particle_field(poses=p.reshape((1,-1)))
        self.update_field()
        self.draw()

    def mouse_press_remove(self, event):
        self.event = event

        p = self._pt_xyz(event)
        if p is not None:
            log.info("Removing particle near {}".format(p))
            rp = self._remove_closest_particle(p)
        self.update_particle_field(poses=rp.reshape((1,-1)), add=False)
        self.update_field()
        self.draw()

    def _remove_closest_particle(self, p):
        """removes the closest particle in self.pos to ``p``"""
        #1. find closest pos:
        dp = self.pos - p
        dist2 = (dp*dp).sum(axis=1)
        ind = dist2.argmin()
        rp = self.pos[ind].copy()
        #2. delete
        self.pos = np.delete(self.pos, ind, axis=0)
        return rp

    def _pt_xyz(self, event):
        x0 = event.xdata
        y0 = event.ydata

        f = False
        if event.inaxes == self.g['xy']:
            x = x0
            y = y0
            z = self.slices[0]
            f = True
        if event.inaxes == self.g['yz']:
            x = x0
            y = self.slices[1]
            z = y0
            f = True
        if event.inaxes == self.g['xz']:
            x = self.slices[2]
            y = y0
            z = x0
            f = True

        if f:
            return np.array((z,y,x))
        return None

# FIXME delete this
if __name__ == '__main__':
    im = np.random.randn(10,10,10)
    OrthoViewer(im)
