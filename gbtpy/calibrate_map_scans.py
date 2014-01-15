import astropy.io.fits as pyfits
import numpy as np

from .timer import print_timing


def load_data_file(filename, extension=1, dataarr=None, datapfits=None):
    """
    Load the series of spectra from a raw SDFITS file
    """

    try:
        print "Reading file using pyfits...",
        filepyfits = pyfits.open(filename,memmap=True)
        datapyfits = filepyfits[extension].data
    except (TypeError,ValueError):
        print "That failed, so trying to treat it as a file...",
        try:
            datapyfits = filename[extension].data
        except AttributeError:
            datapyfits = filename
    if dataarr is None:
        dataarr = datapyfits['DATA']
    print "Data successfully read"
    namelist = datapyfits.names
    data = datapyfits

    if dataarr.sum() == 0 or dataarr[-1,:].sum() == 0:
        print "Reading file using pfits because pyfits didn't read any values!"
        import pfits
        if datapfits is not None:
            data = datapfits
        else:
            data = pfits.FITS(filename).get_hdus()[1].get_data()

        dataarr = np.reshape(data['DATA'],data['DATA'].shape[::-1])

        namelist = data.keys()

    return data, dataarr, namelist, filepyfits

@print_timing
def calibrate_cube_data(filename, outfilename, scanrange=[], refscan1=0,
        refscan2=0, sourcename=None, feednum=1, sampler=0, return_data=False,
        datapfits=None, dataarr=None, clobber=True, tau=0.0,
        obsmode=None, refscans=None, off_template=None, flag_neg_tsys=True,
        replace_neg_tsys=False, extension=1):
    """

    Parameters
    ----------
    filename : str
        input file name
    outfilename : str
        output file name
    scanrange : 2-tuple
        *DATA SELECTION PARAMETER* Range of scans to include when creating off
        positions
    sourcename : str or None
        *DATA SELECTION PARAMETER* Name of source to include
    feednum : int
        *DATA SELECTION PARAMETER* Feed number to use (1 for single-feed
        systems)
    sampler : str
        *DATA SELECTION PARAMETER* Sampler to create the off for (e.g., 'A9')
    obsmode : str
        *DATA SELECTION PARAMETER* Observation Mode to include (e.g.,
        DecLatMap)
    dataarr : None or np.ndarray
        OPTIONAL input of data array.  If it has already been read, this param
        saves time
    off_template : np.ndarray
        A spectrum representing the 'off' position generated by make_off
        (normalized!)
    """

    data, dataarr, namelist, filepyfits = load_data_file(filename, extension=extension, dataarr=dataarr, datapfits=datapfits)

    newdatadict = dict([(n,[]) for n in namelist])
    formatdict = dict([(t.name,t.format) for t in filepyfits[extension].columns])

    samplers = np.unique(data['SAMPLER'])
    if isinstance(sampler,int):
        sampler = samplers[sampler]

    OK = data['SAMPLER'] == sampler
    OK *= data['FEED'] == feednum
    OK *= np.isfinite(data['DATA'].sum(axis=1))
    OKsource = OK.copy()
    if sourcename is not None:
        OKsource *= (data['OBJECT'] == sourcename)
    if scanrange is not []:
        OKsource *= (scanrange[0] < data['SCAN'])*(data['SCAN'] < scanrange[1])
    if obsmode is not None:
        OKsource *= ((obsmode == data.OBSMODE) + ((obsmode+":NONE:TPWCAL") == data.OBSMODE))
    if sourcename is None and scanrange is None:
        raise IndexError("Must specify a source name and/or a scan range")

    print "Beginning scan selection and calibration for sampler %s and feed %s" % (sampler,feednum)

    CalOff = (data['CAL']=='F')
    CalOn  = (data['CAL']=='T')

    speclen = dataarr.shape[1]

    if type(refscans) == list:
        refarray = np.zeros([len(refscans),speclen])
        LSTrefs  = np.zeros([len(refscans)])
        for II,refscan in enumerate(refscans):
            OKref = OK * (refscan == data['SCAN'])  

            specrefon  = np.median(dataarr[OKref*CalOn,:],axis=0) 
            specrefoff = np.median(dataarr[OKref*CalOff,:],axis=0)
            tcalref    = np.median(data['TCAL'][OKref])
            tsysref    = ( np.mean(specrefoff[speclen*0.1:speclen*0.9]) / 
                    (np.mean((specrefon-specrefoff)[speclen*0.1:speclen*0.9])) * 
                    tcalref + tcalref/2.0 )
            refarray[II] = (specrefon + specrefoff)/2.0
            LSTrefs[II]  = np.mean(data['LST'][OKref])
            if specrefon.sum() == 0 or specrefoff.sum() == 0:
                raise ValueError("All values in reference scan %i are zero" % refscan)
            elif np.isnan(specrefon).sum() > 0 or np.isnan(specrefoff).sum() > 0:
                raise ValueError("Reference scan %i contains a NAN" % refscan)

    elif refscan1 is not None and refscan2 is not None:
        OKref1 = OK * (refscan1 == data['SCAN'])  
        OKref2 = OK * (refscan2 == data['SCAN'])  
        
        specref1on  = np.median(dataarr[OKref1*CalOn,:],axis=0) 
        specref1off = np.median(dataarr[OKref1*CalOff,:],axis=0)
        tcalref1    = np.median(data['TCAL'][OKref1])
        tsysref1    = ( np.mean(specref1off[speclen*0.1:speclen*0.9]) / 
                (np.mean((specref1on-specref1off)[speclen*0.1:speclen*0.9])) * 
                tcalref1 + tcalref1/2.0 )
        specref1 = (specref1on + specref1off)/2.0
        LSTref1 = np.mean(data['LST'][OKref1])
        if specref1on.sum() == 0 or specref1off.sum() == 0:
            raise ValueError("All values in reference 1 are zero")
        elif np.isnan(specref1on).sum() > 0 or np.isnan(specref1off).sum() > 0:
            raise ValueError("Reference 1 contains a NAN")

        specref2on  = np.median(dataarr[OKref2*CalOn,:],axis=0) 
        specref2off = np.median(dataarr[OKref2*CalOff,:],axis=0)
        tcalref2    = np.median(data['TCAL'][OKref2])
        tsysref2    = ( np.mean(specref2off[speclen*0.1:speclen*0.9]) / 
                (np.mean((specref2on-specref2off)[speclen*0.1:speclen*0.9])) * 
                tcalref2 + tcalref2/2.0 )
        specref2 = (specref2on + specref2off)/2.0
        LSTref2 = np.mean(data['LST'][OKref2])
        LSTspread = LSTref2 - LSTref1
        if specref2on.sum() == 0 or specref2off.sum() == 0:
            raise ValueError("All values in reference 2 are zero")
        elif np.isnan(specref2on).sum() > 0 or np.isnan(specref2off).sum() > 0:
            raise ValueError("Reference 2 contains a NAN")

    print "Beginning calibration of %i scans." % ((OKsource*CalOn).sum())

    if ((OKsource*CalOn).sum()) == 0:
        import pdb; pdb.set_trace()

    # compute TSYS on a scan-by-scan basis to avoid problems with saturated TSYS.
    scannumbers = np.unique(data['SCAN'][OKsource])
    for scanid in scannumbers:
        whscan = data['SCAN'] == scanid

        on_data = dataarr[whscan*CalOn,speclen*0.1:speclen*0.9]
        off_data = dataarr[whscan*CalOff,speclen*0.1:speclen*0.9]
        tcal = np.median(data['TCAL'][whscan])

        offmean = np.median(off_data,axis=0).mean()
        onmean  = np.median(on_data,axis=0).mean()
        diffmean = onmean-offmean

        tsys = ( offmean / diffmean * tcal + tcal/2.0 )
        print "Scan %4i:  TSYS=%12.3f" % (scanid,tsys)
        data['TSYS'][whscan] = tsys
    
    for specindOn,specindOff in zip(np.where(OKsource*CalOn)[0],np.where(OKsource*CalOff)[0]):

        for K in namelist:
            if K != 'DATA':
                newdatadict[K].append(data[K][specindOn])
            else:
                newdatadict['DATA'].append(np.zeros(4096))

        specOn = dataarr[specindOn,:]
        specOff = dataarr[specindOff,:]
        spec = (specOn + specOff)/2.0
        LSTspec = data['LST'][specindOn]

        if refscans is not None:
            refscannumber = np.argmin(np.abs(LSTspec-LSTrefs))
            if refscannumber == len(refscans) - 1 or LSTrefs[refscannumber] > LSTspec:
                r1 = refscannumber - 1
                r2 = refscannumber 
            elif LSTrefs[refscannumber] < LSTspec:
                r1 = refscannumber
                r2 = refscannumber + 1 
            LSTref1 = LSTrefs[r1]
            LSTref2 = LSTrefs[r2]
            specref1 = refarray[r1,:]
            specref2 = refarray[r2,:]
            LSTspread = LSTref2-LSTref1

        specRef = (specref2-specref1)/LSTspread*(LSTspec-LSTref1) + specref1 # LINEAR interpolation between refs

        # use a templated OFF spectrum
        # (e.g., one that has had spectral lines interpolated over)
        if off_template is not None and off_template.shape == specRef.shape:
            #import pdb; pdb.set_trace()
            specRef = off_template * specRef.mean() / off_template.mean()

        tsys = data['TSYS'][specindOn]

        calSpec = (spec-specRef)/specRef * tsys * np.exp(tau)
        if calSpec.sum() == 0:
            raise ValueError("All values in calibrated spectrum are zero")

        newdatadict['TSYS'][-1] = tsys
        newdatadict['DATA'][-1] = calSpec

    # how do I get the "Format" for the column definitions?

    # Make Table
    cols = [pyfits.Column(name=key,format=formatdict[key],array=value)
        for key,value in newdatadict.iteritems()]
    colsP = pyfits.ColDefs(cols)
    #tablehdu = copy.copy(filepyfits[extension])
    #tablehdu.data = colsP
    # this lies and claims corrupted 
    tablehdu = pyfits.new_table(colsP, header=filepyfits[extension].header)
    phdu = pyfits.PrimaryHDU(header=filepyfits[0].header)
    hdulist = pyfits.HDUList([phdu,tablehdu])
    hdulist.writeto(outfilename,clobber=clobber)
    
    #tablehdu.writeto(outfilename,clobber=clobber)

    if return_data:
        return filepyfits,data,colsP


