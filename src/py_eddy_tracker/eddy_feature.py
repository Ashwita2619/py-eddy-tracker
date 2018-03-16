# -*- coding: utf-8 -*-
"""
===========================================================================
This file is part of py-eddy-tracker.

    py-eddy-tracker is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    py-eddy-tracker is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with py-eddy-tracker.  If not, see <http://www.gnu.org/licenses/>.

Copyright (c) 2014-2015 by Evan Mason
Email: emason@imedea.uib-csic.es
===========================================================================

Version 2.0.3

===========================================================================

"""

import logging
from numpy import ones, where, empty, array
from scipy.ndimage import minimum_filter
from scipy.ndimage import binary_erosion
from matplotlib.figure import Figure
from .tools import winding_number_poly, poly_contain_poly, index_from_nearest_path, \
    index_from_nearest_path_with_pt_in_bbox


class Amplitude(object):
    """
    Class to calculate *amplitude* and counts of *local maxima/minima*
    within a closed region of a sea level anomaly field.
    """
    
    __slots__ = (
        'h_0',
        'data',
        'ix',
        'slice_x',
        'slice_y',
        'iy',
        'interval',
        'amplitude',
        'local_extrema',
        'local_extrema_inds',
        'mle',
        )

    def __init__(self, i_contour_x, i_contour_y, contour_height, data, interval):
        # Height of the contour
        self.h_0 = contour_height
        # Step between two level
        self.interval = interval
        # Indices of all pixels in contour
        self.ix = i_contour_x.copy()
        self.slice_x = slice(self.ix.min(), self.ix.max() + 1)
        self.ix -= self.slice_x.start
        self.iy = i_contour_y.copy()
        self.slice_y = slice(self.iy.min(), self.iy.max() + 1)
        self.iy -= self.slice_y.start
        # Link on original grid (local view)
        self.data = data[self.slice_x, self.slice_y]
        # Amplitude which will be provide
        self.amplitude = 0
        self.local_extrema = None
        self.local_extrema_inds = None
        # Maximum local extrema accepted
        self.mle = 1

    def within_amplitude_limits(self):
        """
        """
        return True
        return self.eddy.ampmin <= self.amplitude <= self.eddy.ampmax

    def _set_cyc_amplitude(self):
        """Get amplitude for cyclone
        """
        self.amplitude = self.h_0 - self.data.min()

    def _set_acyc_amplitude(self):
        """Get amplitude for anticyclone
        """
        self.amplitude = self.data.max() - self.h_0

    def all_pixels_below_h0(self, level):
        """
        Check CSS11 criterion 1: The SSH values of all of the pixels
        are below a given SSH threshold for cyclonic eddies.
        """
        if (self.sla > self.h_0).any():
            return False  # i.e., with self.amplitude == 0
        else:
            self._set_local_extrema(1)
            if 0 < self.local_extrema <= self.mle:
                self._set_cyc_amplitude()
            elif self.local_extrema > self.mle:
                lmi_j, lmi_i = where(self.local_extrema_inds)
                levnm2 = level - (2 * self.interval)
                slamin = 1e5
                for j, i in zip(lmi_j, lmi_i):
                    if slamin >= self.sla[j, i]:
                        slamin = self.sla[j, i]
                        jmin, imin = j, i
                    if self.sla[j, i] >= levnm2:
                        self._set_cyc_amplitude()
                        # Prevent further calls to_set_cyc_amplitude
                        levnm2 = 1e5
                return imin, jmin
        return False

    def all_pixels_above_h0(self, level):
        """
        Check CSS11 criterion 1: The SSH values of all of the pixels
        are above a given SSH threshold for anticyclonic eddies.
        """
        sla = self.data[self.ix, self.iy]
        if (sla < self.h_0).any():
            # i.e.,with self.amplitude == 0
            return False
        else:
            self._set_local_extrema(-1)
            # If we have a number of extrema avoid, we compute amplitude
            if 0 < self.local_extrema <= self.mle:
                self._set_acyc_amplitude()

            # More than avoid
            elif self.local_extrema > self.mle:
                # index of extrema
                lmi_i, lmi_j = where(self.local_extrema_inds)
                levnp2 = level + (2 * self.interval)
                slamax = -1e5
                # Iteration on extrema
                for i, j in zip(lmi_i, lmi_j):
                    # We iterate on max and search the first sup of slamax
                    if slamax <= self.data[i, j]:
                        slamax = self.data[i, j]
                        imax, jmax = i, j

                    if self.data[i, j] <= levnp2:
                        self._set_acyc_amplitude()
                        # Prevent further calls to_set_acyc_amplitude
                        levnp2 = -1e5
                return imax + self.slice_x.start, jmax + self.slice_y.start
        return False

    def _set_local_extrema(self, sign):
        """
        Set count of local SLA maxima/minima within eddy
        """
        # mask of minima
        self.local_extrema_inds = self.detect_local_minima(self.data * sign)
        # nb of minima
        self.local_extrema = self.local_extrema_inds.sum()

    @staticmethod
    def detect_local_minima(grid):
        """
        Take an array and detect the troughs using the local maximum filter.
        Returns a boolean mask of the troughs (i.e., 1 when
        the pixel's value is the neighborhood maximum, 0 otherwise)
        http://stackoverflow.com/questions/3684484/peak-detection-in-a-2d-array/3689710#3689710
        """
        # Equivalent
        neighborhood = ones((3, 3), dtype='bool')
        # ~ neighborhood = generate_binary_structure(grid.ndim, 2)

        # Get local mimima
        detected_minima = minimum_filter(
            grid, footprint=neighborhood) == grid
        background = (grid == 0)
        # Aims ?
        eroded_background = binary_erosion(
            background, structure=neighborhood, border_value=1)
        detected_minima ^= eroded_background
        # mask of minima
        return detected_minima


class Contours(object):
    """
    Class to calculate average geostrophic velocity along
    a contour, *uavg*, and return index to contour with maximum
    *uavg* within a series of closed contours.

    Attributes:
      contour:
        A matplotlib contour object of high-pass filtered SLA

      eddy:
        A tracklist object holding the SLA data

      grd:
        A grid object
    """
    __slots__ = (
        'contours',
        'x_value',
        'y_value',
        'contour_index',
        'level_index',
        'x_min_per_contour',
        'y_min_per_contour',
        'x_max_per_contour',
        'y_max_per_contour',
        'nb_pt_per_contour',
        'nb_contour_per_level',
        '_is_valid',
    )

    def __init__(self, x, y, z, levels):
        """
        c_i : index to contours
        l_i : index to levels
        """
        logging.debug('Start computing iso lines')
        fig = Figure()
        ax = fig.add_subplot(111)
        self.contours = ax.contour(x, y, z, levels)
        logging.debug('Finish computing iso lines')

        nb_level = 0
        nb_contour = 0
        nb_pt = 0
        # Count level and contour
        for i, collection in enumerate(self.contours.collections):
            collection.get_nearest_path_bbox_contain_pt = \
                lambda x, y, i=i: self.get_index_nearest_path_bbox_contain_pt(i, x, y)
            nb_level += 1
            for contour in collection.get_paths():
                contour.used = False
                nb_contour += 1
                nb_pt += contour.vertices.shape[0]
        # Type for coordinates
        coord_dtype = contour.vertices.dtype

        # Array declaration
        self.x_value = empty(nb_pt, dtype=coord_dtype)
        self.y_value = empty(nb_pt, dtype=coord_dtype)

        self.level_index = empty(nb_level, dtype='u4')
        self.nb_contour_per_level = empty(nb_level, dtype='u4')

        self.nb_pt_per_contour = empty(nb_contour, dtype='u4')

        self.x_min_per_contour = empty(nb_contour, dtype=coord_dtype)
        self.x_max_per_contour = empty(nb_contour, dtype=coord_dtype)
        self.y_min_per_contour = empty(nb_contour, dtype=coord_dtype)
        self.y_max_per_contour = empty(nb_contour, dtype=coord_dtype)

        # ~ self._is_valid = empty((nb_contour), dtype='bool')

        # Filled array
        i_pt = 0
        i_c = 0
        i_l = 0
        for collection in self.contours.collections:
            self.level_index[i_l] = i_c
            for contour in collection.get_paths():
                nb_pt = contour.vertices.shape[0]
                # Copy pt
                self.x_value[i_pt:i_pt + nb_pt] = contour.vertices[:, 0]
                self.y_value[i_pt:i_pt + nb_pt] = contour.vertices[:, 1]

                # Set bbox
                self.x_min_per_contour[i_c], self.y_min_per_contour[i_c] = \
                    contour.vertices.min(axis=0)
                self.x_max_per_contour[i_c], self.y_max_per_contour[i_c] = \
                    contour.vertices.max(axis=0)

                # Count pt
                self.nb_pt_per_contour[i_c] = nb_pt
                i_pt += nb_pt
                i_c += 1
            i_l += 1

        self.contour_index = array(
            self.nb_pt_per_contour.cumsum() - self.nb_pt_per_contour,
            dtype='u4'
        )
        self.level_index[0] = 0
        self.nb_contour_per_level[:-1] = self.level_index[1:] - self.level_index[:-1]
        self.nb_contour_per_level[-1] = nb_contour - self.level_index[-1]

    def iter(self, start=None, stop=None, step=None):
        return self.contours.collections[slice(start, stop, step)]

    @property
    def cvalues(self):
        return self.contours.cvalues

    @property
    def levels(self):
        return self.contours.levels

    def get_index_nearest_path_bbox_contain_pt(self, level, xpt, ypt):
        """Get index from the nearest path in the level, if the bbox of the
        path contain pt
        """
        index = index_from_nearest_path_with_pt_in_bbox(
            level,
            self.level_index,
            self.nb_contour_per_level,
            self.nb_pt_per_contour,
            self.contour_index,
            self.x_value,
            self.y_value,
            self.x_min_per_contour,
            self.y_min_per_contour,
            self.x_max_per_contour,
            self.y_max_per_contour,
            xpt,
            ypt
            )
        if index is None:
            return None
        else:
            return self.contours.collections[level]._paths[index]


def get_uavg(grid, all_contours, centlon_e, centlat_e, original_contour, anticyclonic_search, level_start):
    """
    Calculate geostrophic speed around successive contours
    Returns the average
    """
    average_speed = grid.speed_coef(original_contour).mean()
    speed_array = [average_speed]
    pixel_min = 1

    eddy_contours = [original_contour]
    inner_contour = selected_contour = original_contour
    # Must start only on upper or lower contour, no need to test the two part
    for coll in all_contours.iter(start=level_start + 1, step=1 if anticyclonic_search else -1):
        level_contour = coll.get_nearest_path_bbox_contain_pt(centlon_e, centlat_e)
        # Leave loop if no contours at level
        if level_contour is None:
            break
        # 1. Ensure polygon_i contains point centlon_e, centlat_e
        if winding_number_poly(centlon_e, centlat_e, level_contour.vertices) == 0:
            break
        # 2. Ensure polygon_i is within polygon_e
        if not poly_contain_poly(original_contour.vertices, level_contour.vertices):
            break
        # 3. Respect size range
        # if not (pixel_min <= level_contour.nb_pixel<= eddy.pixel_threshold[1]):
        #     break

        # Interpolate uspd to seglon, seglat, then get mean
        level_average_speed = grid.speed_coef(level_contour).mean()
        speed_array.append(level_average_speed)
        if level_average_speed >= average_speed:
            average_speed = level_average_speed
            selected_contour = level_contour
        inner_contour = level_contour
        eddy_contours.append(level_contour)
    for contour in eddy_contours:
        contour.used = True
    return average_speed, selected_contour, inner_contour, speed_array