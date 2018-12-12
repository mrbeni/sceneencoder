import os
import subprocess
import spliter
import json
import sys


def main():
    file_name = sys.argv[1]
    destination = os.path.basename(os.path.splitext(file_name)[0])
    reference_properties = first_pass(file_name)
    bitrate = calculate_ladder(reference_properties)
    scenes = spliter.spliter(file_name, 55, reference_properties['avg_frame_rate'])
    widths = (270, 360, 480, 640, 854, 1280, 1920)

    scenes_270 = list()
    scenes_360 = list()
    scenes_480 = list()
    scenes_640 = list()
    scenes_854 = list()
    scenes_1280 = list()
    scenes_1920 = list()

    final_scene_lists = {
        270: scenes_270,
        360: scenes_360,
        480: scenes_480,
        640: scenes_640,
        854: scenes_854,
        1280: scenes_1280,
        1920: scenes_1920
    }

    for i, scene in enumerate(scenes):
        reference_scene = destination + '-reference-scene-' + str(i+1)
        compressed_scene = destination + '-scene-' + str(i+1)
        reference_transcode(file_name, reference_properties, scene[0], scene[1], reference_scene)
        transcode(file_name, bitrate, reference_properties, scene[0], scene[1], compressed_scene)
        for j in widths:
            reference_file = reference_scene + '-' + str(j) + 'p.mp4'
            compressed_file = compressed_scene + '-' + str(j) + 'p.ts'

            profile_psnr = calculate_psnr(reference_file, compressed_file)
            if profile_psnr > 42:
                transcode(file_name, bitrate, reference_properties, scene[0], scene[1], compressed_scene, j, 1)
            elif profile_psnr < 38:
                transcode(file_name, bitrate, reference_properties, scene[0], scene[1], compressed_scene, j, -1)
            elif 39 < profile_psnr < 42:
                pass
            final_scene_lists[j].append(compressed_file)

    for i in widths:
        concatenate_scenes(final_scene_lists[i], i)


def get_properties(file_name):
    print('get properties...')
    shell_args = ['/usr/local/bin/ffprobe', file_name, '-of', 'json', '-hide_banner', '-show_streams', '-loglevel',
                  'error', '-select_streams', 'v']

    try:
        file_properties = json.loads(
            subprocess.Popen(shell_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf8').communicate()
            [0])['streams'][0]

    except subprocess.SubprocessError as e:
        print(e)
        return e

    return file_properties


def calculate_psnr(reference_file, compressed_file):
    print('calculate_psnr...')
    destination = './' + os.path.basename(os.path.splitext(compressed_file)[0]) + '.psnr'
    shell_args = ['/usr/local/bin/ffmpeg', '-loglevel', 'info', '-hide_banner', '-i', compressed_file ,
                  '-i', reference_file, '-lavfi', 'psnr', '-f', 'null', '-']
    proc = subprocess.Popen(shell_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tee = subprocess.Popen(['tee', destination], stdin=proc.stderr)
    proc.stderr.close()
    tee.communicate()

    line = str(subprocess.check_output(['tail', '-1', destination]))
    y = float(line.split('y:')[1].split(' ')[0])
    u = float(line.split('u:')[1].split(' ')[0])
    v = float(line.split('v:')[1].split(' ')[0])

    os.remove(destination)

    return int((y + u + v) / 3)


def calculate_ladder(reference_properties):
    print('calculate ladder...')
    reference_width = reference_properties['width']
    reference_height = reference_properties['height']
    # reference_sar = reference_properties['sample_aspect_ratio'] or '1:1'
    reference_dar = reference_properties['display_aspect_ratio'] or '16:9'
    dar_w = int(reference_dar.split(':')[0])
    dar_h = int(reference_dar.split(':')[1])
    reference_bitrate = int(reference_properties['bit_rate'])
    reference_ladder = (270, 360, 480, 640, 854, 1280, reference_width)
    target_ladder = []
    bitrate_power = float(0.7)
    bufsize_coefficient = float(0.10)
    for i, profile_width in enumerate(reference_ladder):
        profile_height = int((dar_h * profile_width) / dar_w)

        profile_bitrate = int(round(((float(profile_width * profile_height) / float(
            reference_width * reference_height)) ** bitrate_power) * reference_bitrate))
        profile_bufsize = int(profile_bitrate + (profile_bitrate * bufsize_coefficient))
        target_ladder.append((profile_bitrate, profile_bufsize))
    return target_ladder


def first_pass(file_name):
    print('first pass...')
    destination = './' + os.path.basename(os.path.splitext(file_name)[0])
    shell_args = ['/usr/local/bin/ffmpeg', '-loglevel', 'warning', '-hide_banner', '-y', '-i', file_name, '-c:v',
                  'libx264', '-vf', 'setsar=sar=1/1', '-crf', '23', '-an', '-preset', 'veryfast',
                  destination + '-pre.mp4']

    try:
        subprocess.call(shell_args)
        file_properties = get_properties(destination + '-pre.mp4')
    except subprocess.SubprocessError as e:
        return e

    os.remove(destination + '-pre.mp4')
    return file_properties


def reference_transcode(file_name, reference_properties, start_time, duration, output_destination='./'):
    print('reference transcode...')
    reference_width = reference_properties['width']
    frame_rate = str(reference_properties['avg_frame_rate'])
    gop = str(reference_properties['avg_frame_rate'] * 6)
    base_ffmpeg = ['/usr/local/bin/ffmpeg', '-hide_banner', '-y', '-loglevel', 'warning', '-fflags', '+genpts',
                   '-nostdin', '-ss', str(start_time), '-i', file_name]

    profile_270 = ['-c:v', 'libx264', '-r', '15', '-g', '90', '-keyint_min', '90', '-sc_threshold', '0', '-crf',
                   '17', '-vf', 'scale=270:-2,setsar=sar=1/1', '-profile:v', 'high', '-level', '3.0', '-me_method',
                   'umh', '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                   output_destination + '-270p.mp4']

    profile_360 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                   '17', '-vf', 'scale=360:-2,setsar=sar=1/1', '-profile:v', 'high', '-level', '3.0', '-me_method',
                   'umh', '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                   output_destination + '-360p.mp4']

    profile_480 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                   '17', '-vf', 'scale=480:-2,setsar=sar=1/1', '-profile:v', 'high', '-level', '3.0', '-me_method',
                   'umh', '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                   output_destination + '-480p.mp4']

    profile_640 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                   '17', '-vf', 'scale=640:-2,setsar=sar=1/1', '-profile:v', 'high', '-level', '3.1', '-me_method',
                   'umh', '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                   output_destination + '-640p.mp4']

    profile_854 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                   '17', '-vf', 'scale=854:-2,setsar=sar=1/1', '-profile:v', 'high', '-level', '3.1', '-me_method',
                   'umh', '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                   output_destination + '-854p.mp4']

    profile_1280 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                    '17', '-vf', 'scale=1280:-2,setsar=sar=1/1', '-profile:v', 'high', '-level', '3.2', '-me_method',
                    'umh', '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                    '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                    '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                    '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                    output_destination + '-1280p.mp4']

    profile_1920 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                    '17', '-vf', 'scale=1920:-2,setsar=sar=1/1', '-profile:v', 'high', '-level', '4.0', '-me_method',
                    'umh', '-me_range', '24', '-refs', '5', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                    '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                    '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                    '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                    output_destination + '-1920p.mp4']

    profiles = {
        270: profile_270,
        360: profile_360,
        480: profile_480,
        640: profile_640,
        854: profile_854,
        1280: profile_1280,
        1920: profile_1920
    }

    profile_list = {}
    command = []
    command.extend(base_ffmpeg)
    width = profiles.keys()
    top_quality = [i for i in width if i <= int(reference_width)]
    for i in top_quality:
        profile_list[i] = profiles[i]
        command.extend(profile_list.get(i))

    try:
        subprocess.call(command)
        return 'finished'
    except subprocess.SubprocessError as e:
        return e


def transcode(file_name, bit_rate, reference_properties, start_time, duration, output_destination='./',
              qualities='all', crf_factor=0):
    print('transcode...')
    reference_width = reference_properties['width']
    avg_frame_rate = reference_properties['avg_frame_rate']
    if '/' in avg_frame_rate:
        dividend, divisor = avg_frame_rate.split('/')
    frame_rate = float(dividend) / float(divisor)
    gop = str(frame_rate * 6)
    # print(gop + ' gop is that and avg framrate is this ' + str(frame_rate))

    base_ffmpeg = ['/usr/local/bin/ffmpeg', '-hide_banner', '-y', '-loglevel', 'warning', '-fflags', '+genpts',
                   '-nostdin', '-ss', str(start_time), '-i', file_name]

    profile_270 = ['-c:v', 'libx264', '-r', '15', '-g', '90', '-keyint_min', '90', '-sc_threshold', '0', '-crf',
                   str(25 + crf_factor), '-vf', 'scale=270:-2,setsar=sar=1/1', '-maxrate', str(bit_rate[0][0]),
                   '-bufsize', str(bit_rate[0][1]), '-profile:v', 'high', '-level', '3.0', '-me_method', 'umh',
                   '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                   '-f', 'mpegts', output_destination + '-270p.ts']

    profile_360 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                   str(25 + int(crf_factor)), '-vf', 'scale=360:-2,setsar=sar=1/1', '-maxrate', str(bit_rate[1][0]),
                   '-bufsize', str(bit_rate[1][1]), '-profile:v', 'high', '-level', '3.0', '-me_method', 'umh',
                   '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3','-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                   '-f', 'mpegts', output_destination + '-360p.ts']

    profile_480 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                   str(25 + int(crf_factor)), '-vf', 'scale=480:-2,setsar=sar=1/1', '-maxrate', str(bit_rate[2][0]),
                   '-bufsize', str(bit_rate[2][1]), '-profile:v', 'high', '-level', '3.0', '-me_method', 'umh',
                   '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                   '-f', 'mpegts', output_destination + '-480p.ts']

    profile_640 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                   str(24 + int(crf_factor)), '-vf', 'scale=640:-2,setsar=sar=1/1', '-maxrate', str(bit_rate[3][0]),
                   '-bufsize', str(bit_rate[3][1]), '-profile:v', 'high', '-level', '3.1', '-me_method', 'umh',
                   '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                   '-f', 'mpegts', output_destination + '-640p.ts']

    profile_854 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                   str(24 + int(crf_factor)), '-vf', 'scale=854:-2,setsar=sar=1/1', '-maxrate', str(bit_rate[4][0]),
                   '-bufsize', str(bit_rate[4][1]), '-profile:v', 'high', '-level', '3.1', '-me_method', 'umh',
                   '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                   '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                   '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                   '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1','-map_chapters', '-1',
                   '-f', 'mpegts', output_destination + '-854p.ts']

    profile_1280 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                    str(23 + int(crf_factor)), '-vf', 'scale=1280:-2,setsar=sar=1/1', '-maxrate', str(bit_rate[5][0]),
                    '-bufsize', str(bit_rate[5][1]), '-profile:v', 'high', '-level', '3.2', '-me_method', 'umh',
                    '-me_range', '24', '-refs', '6', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                    '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                    '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2','-trellis', '2',
                    '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                    '-f', 'mpegts', output_destination + '-1280p.ts']

    profile_1920 = ['-c:v', 'libx264', '-r', str(frame_rate), '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-crf',
                    str(23 + int(crf_factor)), '-vf', 'scale=1920:-2,setsar=sar=1/1', '-maxrate', str(bit_rate[6][0]),
                    '-bufsize', str(bit_rate[6][1]), '-profile:v', 'high', '-level', '4.0', '-me_method', 'umh',
                    '-me_range', '24', '-refs', '5', '-subq', '6', '-direct-pred', 'auto', '-partitions', 'all',
                    '-flags', '+loop', '-x264-params', 'deblock=2:2', '-b-pyramid', 'normal', '-bf', '3', '-mixed-refs',
                    '1', '-weightb', '1', '-8x8dct', '1', '-fast-pskip', '0', '-b_strategy', '2', '-trellis', '2',
                    '-rc-lookahead', '60', '-an', '-t', str(duration), '-map_metadata', '-1', '-map_chapters', '-1',
                    '-f', 'mpegts', output_destination + '-1920p.ts']

    profiles = {
        270: profile_270,
        360: profile_360,
        480: profile_480,
        640: profile_640,
        854: profile_854,
        1280: profile_1280,
        1920: profile_1920
    }

    profile_list = {}
    command = []
    command.extend(base_ffmpeg)
    width = profiles.keys()
    if qualities == 'all':
        width = profiles.keys()
        top_quality = [i for i in width if i <= int(reference_width)]
        for i in top_quality:
            profile_list[i] = profiles[i]
            command.extend(profile_list.get(i))
    else:
        for i in [qualities]:
            command.extend(profiles.get(i))

    try:
        subprocess.call(command)
        return 'finished'
    except subprocess.SubprocessError as e:
        return e


def concatenate_scenes(scenes, file_name):
    print('concatinating...')

    shell_args = ['/usr/local/bin/ffmpeg', '-y', '-hide_banner', '-i', 'concat:' + '|'.join(scenes), '-c:v', 'copy',
                    str(file_name) + '.mp4']

    try:
        subprocess.call(shell_args)
    except subprocess.SubprocessError as e:
        return e

    for i in scenes:
        os.remove(i)


if __name__ == "__main__":
        main()
