from tqdm import tqdm
import os
import math
import numpy as np
from scipy import ndimage

from processingmm import libmpMuelMat
from processingmm.multi_img_processing import remove_already_computed_directories, get_calibration_directory
from processingmm.helpers import get_wavelength, save_file_as_npz, rotate_maps_90_deg, load_parameter_names
from processingmm.AzimuthStdViz import AzimuthStdViz

def compute_analysis_python(measurements_directory: str, calib_directory_dates_num: list, calib_directory: str, to_compute: list, PDDN = False, remove_reflection = True,
                            folder_eu_time: dict = {}, run_all = False, batch_processing = False, Flag = False):
    """
    run the script for all the measurement folders in the directory given as an input

    Parameters
    ----------
    measurements_directory : str
        the path to the directory containing the measurements
    calib_directory_dates_num : list of datetime
        a list containing the dates of the calibration folders
    calib_directory : str
        the path to the calibration directory
    to_compute : list
        the list of folders to be computed
    remove_reflection : boolean
        indicates wether or not the reflections of the image should be removed (default: True)
    run_all : boolean
        boolean indicating wether or not all the folders should be processed or only the unprocessed ones (default: False)
    batch_processing : boolean
        boolean indicating if we are batch processing or not (and hence if there is a progress bar, default: False)
    Flag : boolean
        boolean indicating if the warnings should be displayed (default: False)
    
    Returns
    -------
    MuellerMatrices : dict
        the mueller matrices for the different measurement folders
    calibration_directories : dict
        the calibration folders used for the different computations
    """
    MuellerMatrices = {}
    calibration_directories = {}
    
    if run_all:
        treshold = 1000
    else:
        treshold = 21
    
    # iterate over the list of folders to be computed
    if not batch_processing:
        with tqdm(total = len(to_compute)) as pbar:
            for c in to_compute:
                calibration_directory_closest = compute_one_MM(measurements_directory, calib_directory_dates_num, calib_directory, 
                                            MuellerMatrices, treshold, c, PDDN = PDDN, folder_eu_time = folder_eu_time, remove_reflection = remove_reflection, pbar = pbar, Flag = Flag)
                calibration_directories[c] = calibration_directory_closest
    else:
        for c in to_compute:
            calibration_directory_closest = compute_one_MM(measurements_directory, calib_directory_dates_num, calib_directory,
                                                    MuellerMatrices, treshold, c, PDDN = PDDN, folder_eu_time = folder_eu_time, remove_reflection = remove_reflection, Flag = Flag)
            calibration_directories[c] = calibration_directory_closest
    return MuellerMatrices, calibration_directories


def compute_one_MM(measurements_directory: str, calib_directory_dates_num: list, calib_directory: str, MuellerMatrices: dict, 
                   treshold: int, c: str, PDDN = False, folder_eu_time: dict = {}, remove_reflection = True, pbar = None, Flag = False):
    """
    compute_one_MM is a function that computes the MM for the folders in c

    Parameters
    ----------
    measurements_directory : str
        the path to the directory containing the measurements
    calib_directory_dates_num : list of datetime
        a list containing the dates of the calibration folders
    calib_directory : str
        the path to the calibration directory
    MuellerMatrices : dict
        the dictionnary containing the computed Mueller Matrices
    treshold : int
        the number of files that should be found in the folder to consider it processed
    c : str
        the folder name
    remove_reflection : boolean
        indicates wether or not the reflections of the image should be removed (default: True)
    pbar : progress bar
        the progress bar that should (or not) be processed (default None)
    Flag : boolean
        boolean indicating if the warnings should be displayed (default: False)
    
    Returns
    -------
    calibration_directory_closest : str
        the path to the calibration folder that will be used
    """
    path = os.path.join(measurements_directory, c)
    directories = remove_already_computed_directories(path, treshold)
    
    try:
        with open(os.path.join(path, 'annotation', 'rotation_MM.txt')) as f:
            lines = f.readlines()
            angle_correction = int(lines[0])
    except:
        angle_correction = 0
    
    # get the corresponding calibration_directory
    calibration_directory_closest = get_calibration_directory(calib_directory_dates_num, path, calib_directory, directories, folder_eu_time = folder_eu_time, Flag = Flag)
    
    for d in directories:
                        
        # get the wavelength for the folder name
        wavelength = get_wavelength(d)
        calibration_directory_wl = os.path.join(calibration_directory_closest, str(wavelength) + 'nm')
            
        files = os.listdir(calibration_directory_wl)
            
        # load the calibration data
        if str(wavelength) +'_A.cod' in files and str(wavelength) +'_W.cod' in files:
            A = libmpMuelMat.read_cod_data_X3D(os.path.join(calibration_directory_wl, str(wavelength) +'_A.cod'), isRawFlag = 0)
            W = libmpMuelMat.read_cod_data_X3D(os.path.join(calibration_directory_wl, str(wavelength) +'_W.cod'), isRawFlag = 0)
        else:
           A, W = libmpMuelMat.calib_System_AW(calibration_directory_wl, wlen = wavelength)[0:2]

        # load the measurement intensities
        try:
            if PDDN:
                I = libmpMuelMat.read_cod_data_X3D(os.path.join(d, str(wavelength) +'_Intensite_PDDN.cod'), isRawFlag = 0)
            else:
                I = libmpMuelMat.read_cod_data_X3D(os.path.join(d, str(wavelength) +'_Intensite.cod'), isRawFlag = 0)
        except:
            if PDDN:
                try:
                    I = libmpMuelMat.read_cod_data_X3D(os.path.join(d, str(wavelength) +'_Intensite_PDDN.cod'), isRawFlag = 1)
                except:
                    raise ValueError("No PDDN file found")
            else:
                I = libmpMuelMat.read_cod_data_X3D(os.path.join(d, str(wavelength) +'_Intensite.cod'), isRawFlag = 1)
                 
        IN = libmpMuelMat.read_cod_data_X3D(os.path.join(d, str(wavelength) +'_Bruit.cod'), isRawFlag = 1)
        
        # eventually, remove the reflections and compute the MM
        if remove_reflection:
            try:
                I, dilated_mask = libmpMuelMat.removeReflections3D(I)
                IN, _ = libmpMuelMat.removeReflections3D(IN)
            except OSError:
                pass

            # I_IN = I - IN
            I_IN = I
            MM_new = libmpMuelMat.process_MM_pipeline(A, I_IN, W, dilated_mask)
        else:
            
            I_IN = I - IN
            MM_new = libmpMuelMat.process_MM_pipeline(A, I_IN, W, I_IN)
            
        # remove the NaNs from the atzimuth measurements
        MM_new['azimuth'] = curate_azimuth(MM_new['azimuth'], d.replace('raw_data', 'polarimetry'))
        
        # apply a rotation corrections if necessary 
        if angle_correction != 0:
            
            parameter_names = load_parameter_names()
            
            for parameter in parameter_names:
                if parameter == 'azimuth':
                    if angle_correction == 90:
                        MM_new[parameter] = rotate_maps_90_deg(MM_new[parameter], azimuth = True)
                    else:
                        MM_new[parameter] = ndimage.rotate(MM_new[parameter], angle = angle_correction, reshape = False)
                        MM_new[parameter] = (MM_new[parameter] - angle_correction) % 180
                else:
                    if angle_correction == 90:
                        MM_new[parameter] = rotate_maps_90_deg(MM_new[parameter])
                    elif angle_correction == 180:
                        MM_new[parameter] = MM_new[parameter][::-1,::-1]
                    else:
                        if parameter == 'Msk':
                            rotated = ndimage.rotate(MM_new[parameter].astype(float), angle = angle_correction, reshape = False)
                            MM_new[parameter] = rotated > 0.5
                        else:
                            rotated = ndimage.rotate(MM_new[parameter], angle = angle_correction, reshape = False)
                            MM_new[parameter] = rotated
                            
        azimuth_stds = AzimuthStdViz.get_and_plots_stds([d.replace('raw_data', 'polarimetry')], 4, azimuth = MM_new['azimuth'], MM_computation = True)
        MM_new['azimuth_local_var'] = azimuth_stds[d.replace('raw_data', 'polarimetry')]
        
        MuellerMatrices[d.replace('raw_data', 'polarimetry')] = MM_new
        MM = MuellerMatrices[d.replace('raw_data', 'polarimetry')]
        
        # save the Mueller matrix as npz file
        save_file_as_npz(MM, os.path.join(d.replace('raw_data', 'polarimetry'), 'MM.npz'))
        
    if pbar is None:
        pass
    else:
        pbar.update(1)
        
    return calibration_directory_closest


def curate_azimuth(azimuth: np.ndarray, folder = None):
    """
    curates the azimuth (i.e. if the value is NaN, assign to the pixel the mean value of the neighboring pixels)

    Parameters
    ----------
    azimuth : array of shape (388, 516)
        azimuth array
    folder : str
        the current processed folder (default: None)
        
    Returns
    -------
    azimuth : array of shape (388, 516)
        the curated azimuth
    """
    counter = 0
    counter_correct = 0

    # check if the azimuth is numerically stable (i.e. no NaN present)
    if not libmpMuelMat._isNumStable(azimuth):
        for idx, x in enumerate(azimuth):
            for idy, y in enumerate(x):
                
                # if the value is NaN
                if math.isnan(y):
                    
                    # obtain the neighboring pixels
                    azi = select_region(azimuth.shape, azimuth, idx, idy)
                    if math.isnan(np.nanmean(azi)):
                        azimuth[idx,idy] = 0
                    
                    # assign to the pixel the mean value of the neighboring pixels
                    azimuth[idx,idy] = np.nanmean(azi)
                    counter += 1
                else:
                    counter_correct += 1
        try:
            assert libmpMuelMat._isNumStable(azimuth)
        except:
            print(folder)
    else:
        pass

    if counter > 1/100*azimuth.shape[0]*azimuth.shape[1]:
        pass        
    return azimuth


def select_region(shape, azimuth, idx, idy):
    """
    select the region that will be used to curate a pixel of the azimuth

    Parameters
    ----------
    shape : tuple
        the shape of the array
    azimuth : array of shape (388, 516)
        azimuth array
    idx, idy : int, int
        the index values of the pixel of interest
        
    Returns
    -------
    azimuth[min_x: max_x, min_y:max_y] : array
        the neighboring pixels
    """
    max_x, min_x = None, None
    max_y, min_y = None, None
    
    # special cases - borders of the image
    if idx == 0:
        min_x = 0
        max_x = 2
    if idy == 0:
        min_y = 0
        max_y = 2
    if idx == shape[0] - 1:
        min_x = shape[0] - 3
        max_x = shape[0] - 1
    if idy == shape[1] - 1:
        min_y = shape[1] - 3
        max_y = shape[1] - 1
    
    # middle of the image
    if max_x == None and min_x == None:
        min_x = idx - 1
        max_x = idx + 2
        
    if max_y == None and min_y == None:
        min_y = idy - 1
        max_y = idy + 2
        
    return azimuth[min_x: max_x, min_y:max_y]