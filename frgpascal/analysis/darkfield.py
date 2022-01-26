from tifffile import imread
import numpy as np
from skimage.filters import threshold_local

""""
A collection of functions for analyzing darkfield images.
"""


def load_image(fid, red_only: bool = True):
    """
    Load an image from a filepath. Defaults to load only the red channel.
    """
    img = imread(fid) * 64 * 255
    img = img.astype(np.float32)
    if red_only == True:
        return img[:, :, 0]
    else:
        return img


def get_median(im):
    """
    From an imported image, get the median pixel value.

    Used as a coarse haze metric (hazier film = higher median counts on darkfield image)
    """
    if len(im.shape) == 2:
        pass
    elif len(im.shape) == 3:
        # If RGB, take red column, the first column.
        im = im[:, :, 0]
        print(
            "Careful! Image entered as RGB, not single channel. Red channel was used."
        )
    else:
        print(
            "The image was not in the correct format. Must be RGB or a single channel"
        )
        pass

    median = np.median(im)

    return median


def mask_intensity(im):
    """
    This function uses the 'threshold_local' function of scikit-image
    to mask a given image and return the value of the pixels within the mask.
    """
    # set an offset to be called within the thresholding function.
    # this was determined by trial-and-error and can certainly be changed
    offset = -np.median(im) / 3
    # store the thresholded image to thresh
    # the block_size is the number of pixels considered for a local threshold.
    thresh = threshold_local(im, block_size=541, method="gaussian", offset=offset)
    # convert to binary. this is the mask.
    b_im = im > thresh
    # get the values of the image where b_im == 1
    vals = im[b_im]
    #  return the sum of the pixel values for use as a metric of film quality
    return vals.sum()


# def quality_check(im):
#     median = get_median(im)
#     thresh_val = mask_intensity(im)
#     # in a darkfield image, a lower median pixel intensity is better.
#     # the values below are determined by trial-and-error.
#     if median < 12.0:
#         med = 'excellent'
#     elif median >= 12.0 and median < 20.0:
#         med = 'good'
#     elif median >= 20.0 and median < 32.0:
#         med = 'fair'
#     elif median >=32.0:
#         med = 'poor'
#     else:
#         pass
#     # a lower summed threshold value is better for darkfield images.
#     # the values below are determined by trial-and-error.
#     if thresh_val < 100000.0:
#         thresh = 'excellent'
#     elif thresh_val >= 100000.0 and thresh_val < 200000.0:
#         thresh = 'good'
#     elif thresh_val >= 200000.0 and thresh_val < 400000.0:
#         thresh = 'fair'
#     elif thresh_val >= 400000.0:
#         thresh = 'poor'
#     else:
#         pass

#     return(med, thresh)
