from __future__ import division
from future import standard_library
standard_library.install_aliases()
from past.utils import old_div
from EXOSIMS.Prototypes.PlanetPhysicalModel import PlanetPhysicalModel
import astropy.units as u
import astropy.constants as const
import numpy as np
import scipy.interpolate as interpolate
import os, inspect
try:
    import pickle as pickle
except:
    import pickle


class FortneyMarleyCahoyMix1(PlanetPhysicalModel):
    """
    Planet density models based on Fortney & Marley, albedo models based on 
    Cahoy.  Intended for use with the Kepler-like planet population modules.
    
    Args: 
        \*\*specs: 
            user specified values
            
    Attributes: 
                
    
    Notes:  
    1. The calculation of albedo is based solely on the semi-major axis
    and uses a uniform distribution of metallicities to interpolate albedo from 
    the grid in Cahoy et al. 2010. 
    
    """

    def __init__(self, **specs):
        
        PlanetPhysicalModel.__init__(self, **specs)
        
        #define albedo interpolant:
        smas = [0.8,2,5,10]
        fes = [1,3,10,30]
        ps = np.array([[0.322, 0.241, 0.209, 0.142],\
              [0.742, 0.766, 0.728, 0.674],\
              [0.567, 0.506, 0.326, 0.303],\
              [0.386, 0.260, 0.295, 0.279]])
        
        grid_a, grid_fe = np.meshgrid(smas,fes)
        self.albedo_pts = np.vstack((grid_a.flatten(),grid_fe.flatten())).T
        self.albedo_vals = ps.T.flatten()
        
        #define conversion functions for icy/rocky/metal planets
        #ice/rock fraction - Fortney et al., 2007 Eq. 7 (as corrected in paper erratum)
        #units are in Earth masses and radii, frac = 1 is pure ice
        self.R_ir = lambda frac,M: (0.0912*frac + 0.1603)*np.log10(M)**2. +\
                (0.333*frac + 0.7387)*np.log10(M) + (0.4639*frac + 1.1193)
        self.M_ir = lambda frac,R: 10.**(old_div((-(0.333*frac + 0.7387) + \
                np.sqrt((0.333*frac + 0.7387)**2. - 4.*(0.0912*frac + 0.1603)*\
                (0.4639*frac + 1.1193 - R))),(2.*(0.0912*frac + 0.1603))))
        
        #rock/iron fraction - Fortney et al., 2007 Eq. 8 (as corrected in paper erratum)
        #units are in Earth masses and radii, frac = 1 is pure rock
        self.R_ri = lambda frac,M: (0.0592*frac + 0.0975)*np.log10(M)**2. + \
                (0.2337*frac + 0.4938)*np.log10(M) + (0.3102*frac + 0.7932)
        self.M_ri = lambda frac,R: 10.**(old_div((-(0.2337*frac + 0.4938) + \
                np.sqrt((0.2337*frac + 0.4938)**2. - 4.*(0.0592*frac + 0.0975) * \
                (0.3102*frac + 0.7932 - R))),(2.*(0.0592*frac + 0.0975))))
        
        #find and load the Fortney et al. Table 4 data (gas giant densities)
        #data is al in Jupiter radii, Earth masses and AU
        classpath = os.path.split(inspect.getfile(self.__class__))[0]
        filename = 'Fortney_etal_2007_table4.p'
        datapath = os.path.join(classpath, filename)
        if not os.path.exists(datapath):
            raise Exception("Gas giant data file not found.")
        self.ggdat = pickle.load( open( datapath, "rb" ) )
        self.ggdat['dist'] = self.ggdat['dist']*u.AU
        self.ggdat['planet_mass'] = self.ggdat['planet_mass']*const.M_earth
        
        Rtmp = self.ggdat['radii'].copy()
        Rtmp *= (old_div(const.R_jup,const.R_earth)).value
        Rtmp[Rtmp != Rtmp] = 0.
        self.giant_pts = np.vstack((self.ggdat['x1'].flatten().astype(float),\
                                    self.ggdat['x3'].flatten().astype(float),\
                                    Rtmp.flatten().astype(float))).T
        self.giant_vals = self.ggdat['x2'].flatten()
        
        self.giant_pts2 = np.vstack((self.ggdat['x1'].flatten().astype(float),\
                                    self.ggdat['x3'].flatten().astype(float),\
                                    self.ggdat['x2'].flatten().astype(float))).T
        self.giant_vals2 = Rtmp.flatten().astype(float)
        
        self.ggdat['radii'] = self.ggdat['radii']*const.R_jup

    def calc_albedo_from_sma(self,a):
        """
        Helper function for calculating albedo. We assume a uniform distribution 
        of metallicities, and then interpolate the grid from Cahoy et al. 2010.
        
        Args:
            a (astropy Quanitity array):
               Semi-major axis values
        
        Returns:
            p (ndarray):
                Albedo values
        
        """
        
        #grab the sma values and constrain to grid
        atmp = a.to('AU').value
        atmp[atmp < 0.8] = 0.8;
        atmp[atmp > 10] = 10;
        
        #generate uniform fe grid:
        fetmp = np.random.uniform(size=atmp.size,low=1,high=30)
        
        p = interpolate.griddata(self.albedo_pts, self.albedo_vals,\
                (atmp,fetmp), method='cubic')
        
        return p

    def calc_mass_from_radius(self, Rp):
        """
        Helper function for calculating mass given the radius.  The calculation
        is done in two steps, first covering all things that can only ice/rock/iron, 
        and then things that can be giants.
        
        Args:
            Rp (astropy Quantity array):
                Planet radius in units of km
        
        Returns:
            Mp (astropy Quantity array):
                Planet mass in units of kg
        
        """
        
        Mp = np.zeros(Rp.shape)
        
        #first, the things up to the min giant radius but greater 
        #than 2 Earth radii (assumed to be icy)
        inds = (Rp <= np.nanmin(self.ggdat['radii'])) & (Rp > 2*const.R_earth)
        Rtmp = Rp[inds]
        fracs = np.random.uniform(size=Rtmp.size, low=0.5,high=1.)
        Mp[inds] = self.M_ir(fracs,(old_div(Rtmp,const.R_earth)).decompose().value)
        
        #everything under 2 Earth radii can by ice/rock/iron
        inds = Rp <= 2*const.R_earth
        Rtmp = Rp[inds]
        Mtmp = np.zeros(Rtmp.shape)
        fracs = np.random.uniform(size=Rtmp.size, low=-1.,high=1.)
        
        #ice/rock and rock/iron
        icerock = fracs < 0
        Mtmp[icerock] = self.M_ir(np.abs(fracs[icerock]),\
                (old_div(Rtmp[icerock],const.R_earth)).decompose().value)
        rockiron = fracs >= 0
        Mtmp[rockiron] = self.M_ri(np.abs(fracs[rockiron]),\
                (old_div(Rtmp[rockiron],const.R_earth)).decompose().value)
        Mp[inds] = Mtmp
        
        #everything else is a giant.  those above the table limit 
        #are inflated close-in things that are undetectable
        inds = Rp > np.nanmax(self.ggdat['radii'])
        Mp[inds] = (old_div(np.max(self.ggdat['planet_mass']),const.M_earth)).value
        
        inds = (Rp > np.nanmin(self.ggdat['radii'])) & (Rp <= np.nanmax(self.ggdat['radii'])) 
        Rtmp = Rp[inds]
        Mtmp = interpolate.griddata(self.giant_pts, self.giant_vals,\
                (np.random.uniform(low=0,high=100,size=Rtmp.size),\
                 np.exp(np.log(0.02)+(np.log(9.5)-np.log(0.02))*np.random.uniform(size=Rtmp.size)),\
                 (old_div(Rtmp,const.R_earth)).decompose().value))
        if np.any(np.isnan(Mtmp)):
            inds2 = np.isnan(Mtmp)
            Mtmp[inds2] = (old_div(((1.33*u.g/u.cm**3.)*4*np.pi*Rtmp[inds2]**3./3.).decompose(),const.M_earth)).value
        Mp[inds] = Mtmp
        
        Mp = Mp*const.M_earth.to('kg')
        
        return Mp

    def calc_radius_from_mass(self, Mp):
        """
        Helper function for calculating radius given the mass.  The calculation
        is done in two steps, first covering all things that can only ice/rock/iron, 
        and then things that can be giants.
        
        Args:
            Mp (astropy Quantity array):
                Planet mass in units of kg
        
        Returns:
            Rp (astropy Quantity array):
                Planet radius in units of km
        
        """
        
        Rp = np.zeros(Mp.shape)
        
        #Everything below the tabulated mass values is treated as
        #ice/rock/iron
        inds = Mp <= np.nanmin(self.ggdat['planet_mass'])
        Mtmp = Mp[inds]
        Rtmp = np.zeros(Mtmp.shape)
        fracs = np.random.uniform(size=Mtmp.size, low=-1.,high=1.)
        
        #ice/rock and rock/iron
        icerock = fracs < 0
        Rtmp[icerock] = self.R_ir(np.abs(fracs[icerock]),\
                (old_div(Mtmp[icerock],const.M_earth)).decompose().value)
        rockiron = fracs >= 0
        Rtmp[rockiron] = self.R_ri(np.abs(fracs[rockiron]),\
                (old_div(Mtmp[rockiron],const.M_earth)).decompose().value)
        Rp[inds] = Rtmp
        
        #everything else is a giant. 
        inds = Mp > np.nanmin(self.ggdat['planet_mass'])
        Mtmp = Mp[inds]
        Rp[inds] = interpolate.griddata(self.giant_pts2, self.giant_vals2,\
                (np.random.uniform(low=0,high=100,size=Mtmp.size),\
                 np.exp(np.log(0.02)+(np.log(9.5)-np.log(0.02))*np.random.uniform(size=Mtmp.size)),\
                 (old_div(Mtmp,const.M_earth)).decompose().value))
        
        #things that failed
        inds = np.isnan(Rp) | (Rp == 0.)
        if np.any(inds):
            rho = 1.33*u.g/u.cm**3.
            Rp[inds] = (old_div((3*Mp[inds]/rho/np.pi/4.)**(old_div(1,3.)),const.R_earth)).decompose().value
        
        Rp = Rp*const.R_earth.to('km')
        
        return Rp

