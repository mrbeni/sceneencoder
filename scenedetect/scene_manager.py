# -*- coding: utf-8 -*-
#
#         PySceneDetect: Python-Based Video Scene Detector
#   ---------------------------------------------------------------
#     [  Site: http://www.bcastell.com/projects/pyscenedetect/   ]
#     [  Github: https://github.com/Breakthrough/PySceneDetect/  ]
#     [  Documentation: http://pyscenedetect.readthedocs.org/    ]
#
# Copyright (C) 2012-2018 Brandon Castellano <http://www.bcastell.com>.
#
# PySceneDetect is licensed under the BSD 2-Clause License; see the included
# LICENSE file, or visit one of the following pages for details:
#  - https://github.com/Breakthrough/PySceneDetect/
#  - http://www.bcastell.com/projects/pyscenedetect/
#
# This software uses the Numpy, OpenCV, click, tqdm, and pytest libraries.
# See the included LICENSE files or one of the above URLs for more information.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
# AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

""" PySceneDetect scenedetect.scene_manager Module

This module implements the SceneManager object, which is used to coordinate
SceneDetectors and frame sources (e.g. VideoManagers, VideoCaptures), creating
a SceneResult object for each detected scene.

The SceneManager also facilitates passing a StatsManager, if any is defined,
to the associated SceneDetectors for caching of frame metrics.
"""

# Standard Library Imports
from __future__ import print_function
import math

# Third-Party Library Imports
import cv2
from scenedetect.platform import tqdm

# PySceneDetect Library Imports
from scenedetect.frame_timecode import FrameTimecode
from scenedetect.platform import get_csv_writer
from scenedetect.stats_manager import FrameMetricRegistered


def write_scene_list(output_csv_file, scene_list, cut_list=None):
    """ Writes the given list of scenes to an output file handle in CSV format.

    Arguments:
        output_csv_file: Handle to open file in write mode.
        scene_list: List of pairs of FrameTimecodes denoting each scene's start/end FrameTimecode.
        cut_list: Optional list of FrameTimecode objects denoting the cut list (i.e. the frames
            in the video that need to be split to generate individual scenes). If not passed,
            the start times of each scene (besides the 0th scene) is used instead.
    """
    # type: (File, List[Tuple[FrameTimecode, FrameTimecode]], Optional[List[FrameTimecode]]) -> None
    csv_writer = get_csv_writer(output_csv_file)
    # Output Timecode List
    csv_writer.writerow(
        ["Timecode List:"] +
        cut_list if cut_list else [start.get_timecode() for start, _ in scene_list[1:]])
    csv_writer.writerow([
        "Scene Number",
        "Start Frame", "Start Timecode", "Start Time (seconds)",
        "End Frame", "End Timecode", "End Time (seconds)",
        "Length (frames)", "Length (timecode)", "Length (seconds)"])
    for i, (start, end) in enumerate(scene_list):
        duration = end - start
        csv_writer.writerow([
            '%d' % (i+1),
            '%d' % start.get_frames(), start.get_timecode(), '%.3f' % start.get_seconds(),
            '%d' % end.get_frames(), end.get_timecode(), '%.3f' % end.get_seconds(),
            '%d' % duration.get_frames(), duration.get_timecode(), '%.3f' % duration.get_seconds()])


class SceneManager(object):
    """ The SceneManager facilitates detection of scenes via the detect_scenes() method,
    given a video source (scenedetect.VideoManager or cv2.VideoCapture), and SceneDetector
    algorithms added via the add_detector() method.

    Can also optionally take a StatsManager instance during construction to cache intermediate
    scene detection calculations, making subsequent calls to detect_scenes() much faster,
    allowing the cached values to be saved/loaded to/from disk, and also manually determining
    the optimal threshold values or other options for various detection algorithms.
    """

    def __init__(self, stats_manager=None):
        # type: (Optional[StatsManager])
        self._cutting_list = []
        self._detector_list = []
        self._stats_manager = stats_manager
        self._num_frames = 0
        self._start_frame = 0


    def add_detector(self, detector):
        # type: (SceneDetector) -> None
        """ Adds/registers a SceneDetector (e.g. ContentDetector, ThresholdDetector) to
        run when detect_scenes is called. The SceneManager owns the detector object,
        so a temporary may be passed.

        Arguments:
            detector (SceneDetector): Scene detector to add to the SceneManager.
        """
        detector.stats_manager = self._stats_manager
        self._detector_list.append(detector)
        if self._stats_manager is not None:
            # Allow multiple detection algorithms of the same type to be added
            # by suppressing any FrameMetricRegistered exceptions due to attempts
            # to re-register the same frame metric keys.
            try:
                self._stats_manager.register_metrics(detector.get_metrics())
            except FrameMetricRegistered:
                pass

    def get_num_detectors(self):
        # type: () -> int
        """ Gets number of registered scene detectors added via add_detector. """
        return len(self._detector_list)


    def clear(self):
        # type: () -> None
        """ Clears all cuts/scenes and resets the SceneManager's position.

        Any statistics generated are still saved in the StatsManager object
        passed to the SceneManager's constructor, and thus, subsequent
        calls to detect_scenes, using the same frame source reset at the
        initial time (if it is a VideoManager, use the reset() method),
        will use the cached frame metrics that were computed and saved
        in the previous call to detect_scenes.
        """
        self._cutting_list.clear()
        self._num_frames = 0
        self._start_frame = 0


    def clear_detectors(self):
        # type: () -> None
        """ Removes all scene detectors added to the SceneManager via add_detector(). """
        self._detector_list.clear()


    def get_scene_list(self, base_timecode):
        # type: (FrameTimecode) -> List[Tuple[FrameTimecode, FrameTimecode]]
        """ Returns a list of tuples of start/end FrameTimecodes for each scene.

        The scene list is generated from the cutting list (get_cut_list), noting that each
        scene is contiguous, starting from the first and ending at the last frame of the input.

        Returns:
            List of tuples in the form (start_time, end_time), where both start_time and
            end_time are FrameTimecode objects representing the exact time/frame where each
            detected scene in the video begins and ends.
        """
        # Scene list, where scenes are tuples of (Start FrameTimecode, End FrameTimecode),
        # and base_timecode is the base FrameTimecode of the video used in detect_scenes.
        scene_list = []
        if not self._cutting_list:
            return scene_list
        cut_list = self.get_cut_list(base_timecode)
        # Initialize last_cut to the first frame we processed,as it will be
        # the start timecode for the first scene in the list.
        last_cut = base_timecode + self._start_frame
        for cut in cut_list:
            scene_list.append((last_cut, cut))
            last_cut = cut
        # Last scene is from last cut to end of video.
        scene_list.append((last_cut, base_timecode + self._num_frames))

        return scene_list


    def get_cut_list(self, base_timecode):
        # type: (FrameTimecode) -> List[FrameTimecode]
        """ Returns a list of FrameTimecodes of the detected scene changes/cuts.

        Unlike get_scene_list, the cutting list returns a list of FrameTimecodes representing
        the point in the input video(s) where a new scene was detected, and thus the frame
        where the input should be cut/split. The cutting list, in turn, is used to generate
        the scene list, noting that each scene is contiguous starting from the first frame
        and ending at the last frame detected.

        Returns:
            List of FrameTimecode objects denoting the points in time where a scene change
            was detected in the input video(s), which can also be passed to external tools
            for automated splitting of the input into individual scenes.
        """

        return [FrameTimecode(cut, base_timecode)
                for cut in self._get_cutting_list()]


    def _get_cutting_list(self):
        # type: () -> list
        """ Returns a sorted list of unique frame numbers of any detected scene cuts. """
        # We remove duplicates here by creating a set then back to a list and sort it.
        return sorted(list(set(self._cutting_list)))


    def _add_cut(self, frame_num):
        # type: (int) -> None
        # Adds a cut to the cutting list.
        self._cutting_list.append(frame_num)


    def _add_cuts(self, cut_list):
        # type: (List[int]) -> None
        # Adds a list of cuts to the cutting list.
        self._cutting_list += cut_list


    def _process_frame(self, frame_num, frame_im):
        # type(int, numpy.ndarray) -> None
        """ Adds any cuts detected with the current frame to the cutting list. """
        for detector in self._detector_list:
            self._add_cuts(detector.process_frame(frame_num, frame_im))


    def _is_processing_required(self, frame_num):
        # type(int) -> bool
        """ Is Processing Required: Returns True if frame metrics not in StatsManager,
        False otherwise.
        """
        return all([detector.is_processing_required(frame_num) for detector in self._detector_list])


    def _post_process(self, frame_num):
        # type(int, numpy.ndarray) -> None
        """ Adds any remaining cuts to the cutting list after processing the last frame. """
        for detector in self._detector_list:
            self._add_cuts(detector.post_process(frame_num))


    def detect_scenes(self, frame_source, start_time=0, end_time=None, frame_skip=0,
                      show_progress=True):
        # type: (VideoManager, Union[int, FrameTimecode],
        #        Optional[Union[int, FrameTimecode]], Optional[bool]) -> int
        """ Perform scene detection on the given frame_source using the added SceneDetectors.

        Blocks until all frames in the frame_source have been processed. Results
        can be obtained by calling the get_scene_list() method afterwards.

        Arguments:
            frame_source (scenedetect.VideoManager or cv2.VideoCapture):  A source of
                frames to process (using frame_source.read() as in VideoCapture).
                VideoManager is preferred as it allows concatenation of multiple videos
                as well as seeking, by defining start time and end time/duration.
            start_time (int or FrameTimecode): Time/frame the passed frame_source object
                is currently at in time (i.e. the frame # read() will return next).
                Must be passed if the frame_source has been seeked past frame 0
                (i.e. calling set_duration on a VideoManager or seeking a VideoCapture).
            end_time (int or FrameTimecode): Maximum number of frames to detect
                (set to None to detect all available frames). Only needed for OpenCV
                VideoCapture objects, as VideoManager allows set_duration.
            frame_skip (int): Number of frames to skip (i.e. process every 1 in N+1
                frames, where N is frame_skip, processing only 1/N+1 percent of the
                video, speeding up the detection time at the expense of accuracy).
            show_progress (bool): If True, and the tqdm module is available, displays
                a progress bar with the progress, framerate, and expected time to
                complete processing the video frame source.
        Returns:
            Number of frames read and processed from the frame source.
        Raises:
            ValueError
        """

        if frame_skip > 0 and self._stats_manager is not None:
            raise ValueError('frame_skip must be 0 when using a StatsManager.')

        start_frame = 0
        curr_frame = 0
        end_frame = None

        total_frames = math.trunc(frame_source.get(cv2.CAP_PROP_FRAME_COUNT))

        if isinstance(start_time, FrameTimecode):
            start_frame = start_time.get_frames()
        elif start_time is not None:
            start_frame = int(start_time)
        self._start_frame = start_frame

        curr_frame = start_frame

        if isinstance(end_time, FrameTimecode):
            end_frame = end_time.get_frames()
        elif end_time is not None:
            end_frame = int(end_time)

        if end_frame is not None:
            total_frames = end_frame
        if start_frame is not None:
            total_frames -= start_frame

        progress_bar = None
        if tqdm and show_progress:
            progress_bar = tqdm(
                total=total_frames, unit='frames')
        try:

            while True:
                if end_frame is not None and curr_frame >= end_frame:
                    break
                # We don't compensate for frame_skip here as the frame_skip option
                # is not allowed when using a StatsManager, and thus processing is
                # always required for all frames when using frame_skip.
                if (self._is_processing_required(self._num_frames + start_frame)
                        or self._is_processing_required(self._num_frames + start_frame + 1)):
                    ret_val, frame_im = frame_source.read()
                else:
                    ret_val = frame_source.grab()
                    frame_im = None

                if not ret_val:
                    break
                self._process_frame(self._num_frames + start_frame, frame_im)

                curr_frame += 1
                self._num_frames += 1
                if progress_bar:
                    progress_bar.update(1)

                if frame_skip > 0:
                    for _ in range(frame_skip):
                        if not frame_source.grab():
                            break
                        curr_frame += 1
                        self._num_frames += 1
                        if progress_bar:
                            progress_bar.update(1)

            self._post_process(curr_frame)

            num_frames = curr_frame - start_frame

        finally:
            if progress_bar:
                progress_bar.close()

        return num_frames

