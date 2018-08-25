
#
# PySceneDetect v0.5 API Test Script
#
# NOTE: This file can only be used with development versions of PySceneDetect,
#       and gives a high-level overview of how the new API will look and work.
#       This file is for development and testing purposes mostly, although it
#       also serves as a base for further example and test programs.
#

# from __future__ import print_function
import os

import scenedetect
from scenedetect.video_manager import VideoManager
from scenedetect.scene_manager import SceneManager
from scenedetect.frame_timecode import FrameTimecode
from scenedetect.stats_manager import StatsManager
from scenedetect.detectors import ContentDetector
from scenedetect.video_splitter import split_video_ffmpeg
from scenedetect.video_splitter import is_ffmpeg_available



def spliter(file_name, frame_rate=25, threshold=55):
    print('detecting scenes...')
    STATS_FILE_PATH = './' + os.path.basename(os.path.splitext(file_name)[0]) + '.csv'
    # print(STATS_FILE_PATH)
    # print(file_name)
    scenes = list()

    # print("Running PySceneDetect API test...")

    # print("PySceneDetect version being used: %s" % str(scenedetect.__version__))

    # Create a video_manager point to video file testvideo.mp4. Note that multiple
    # videos can be appended by simply specifying more file paths in the list
    # passed to the VideoManager constructor. Note that appending multiple videos
    # requires that they all have the same frame size, and optionally, framerate.
    video_manager = VideoManager([file_name])
    stats_manager = StatsManager()
    scene_manager = SceneManager(stats_manager)
    # Add ContentDetector algorithm (constructor takes detector options like threshold).
    scene_manager.add_detector(ContentDetector(threshold=55.0, min_scene_len=288))
    base_timecode = video_manager.get_base_timecode()
    # print(base_timecode)

    try:
        # If stats file exists, load it.
        if os.path.exists(STATS_FILE_PATH):
            # Read stats from CSV file opened in read mode:
            with open(STATS_FILE_PATH, 'r') as stats_file:
                stats_manager.load_from_csv(stats_file, base_timecode)

        start_time = base_timecode + 20  # 00:00:00.667
        end_time = base_timecode + 20.0  # 00:00:20.000
        # Set video_manager duration to read frames from 00:00:00 to 00:00:20.
        video_manager.set_duration(start_time=start_time)
        # , end_time=end_time

        # Set downscale factor to improve processing speed.
        video_manager.set_downscale_factor()

        # Start video_manager.
        video_manager.start()

        # Perform scene detection on video_manager.
        scene_manager.detect_scenes(frame_source=video_manager,
                                    start_time=start_time)

        # Obtain list of detected scenes.
        scene_list = scene_manager.get_scene_list(base_timecode)

        # Like FrameTimecodes, each scene in the scene_list can be sorted if the
        # list of scenes becomes unsorted.

        # print('List of scenes obtained:')
        # for i, scene in enumerate(scene_list):
            # print('    Scene %2d: Start %s / Frame %d, End %s / Frame %d' % (
            #     i+1,
            #     scene[0].get_timecode(), scene[0].get_frames(),
            #     scene[1].get_timecode(), scene[1].get_frames(),))
            # print('scene[0] is {}, scene[1] is {}, i+1 is {}'.format(scene[0], scene[1], i+1) )
            # scenes.append((scene[0], scene[1]))
            # print('-------------------------------------------------------------------------------------------------')
            # print('ffmpeg -ss {} -i testvideo.mp4 -c:v libx264 -t {} -an test-scene-{}.mp4'.format(scene[0],
            #                                                                                        scene[1], i + 1))

        # We only write to the stats file if a save is required:
        if stats_manager.is_save_required():
            with open(STATS_FILE_PATH, 'w') as stats_file:
                stats_manager.save_to_csv(stats_file, base_timecode)

        # is_ffmpeg_available()
        # print(scene_list)


        scenes = split_video_ffmpeg([file_name], scene_list, '$VIDEO_NAME-Scene-$SCENE_NUMBER.mp4',
                           os.path.basename(os.path.splitext(file_name)[0]) + '-reference',
                                    '-c:v libx264 -preset fast -crf 18 -an')


    finally:
        video_manager.release()

    return scenes

# if __name__ == "__main__":
#     main()

