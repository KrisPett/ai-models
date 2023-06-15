import tqdm
import random
import pathlib
import itertools
import collections

import os
import cv2
import numpy as np
import remotezip as rz

import tensorflow as tf

import imageio
from IPython import display
from urllib import request
from tensorflow_docs.vis import embed


def list_files_from_zip_url(zip_url):
    files = []
    with rz.RemoteZip(zip_url) as zip:
        for zip_info in zip.infolist():
            files.append(zip_info.filename)
    return files


def get_class(fname):
    return fname.split('_')[-3]


def get_files_per_class(files):
    files_for_class = collections.defaultdict(list)
    for fname in files:
        class_name = get_class(fname)
        files_for_class[class_name].append(fname)
    return files_for_class


def select_subset_of_classes(files_for_class, classes, files_per_class):
    files_subset = dict()
    for class_name in classes:
        class_files = files_for_class[class_name]
        files_subset[class_name] = class_files[:files_per_class]
    return files_subset


def download_from_zip(zip_url, to_dir, file_names):
    with rz.RemoteZip(zip_url) as zip:
        for fn in tqdm.tqdm(file_names):
            class_name = get_class(fn)
            zip.extract(fn, str(to_dir / class_name))
            unzipped_file = to_dir / class_name / fn
            fn = pathlib.Path(fn).parts[-1]
            output_file = to_dir / class_name / fn
            unzipped_file.rename(output_file)


def split_class_lists(files_for_class, count):
    split_files = []
    remainder = {}
    for cls in files_for_class:
        split_files.extend(files_for_class[cls][:count])
        remainder[cls] = files_for_class[cls][count:]
    return split_files, remainder


def download_ucf_101_subset(zip_url, num_classes, splits, download_dir):
    files = list_files_from_zip_url(zip_url)

    for f in files:
        path = os.path.normpath(f)
        tokens = path.split(os.sep)
        if len(tokens) <= 2:
            files.remove(f)
    files_for_class = get_files_per_class(files)
    classes = list(files_for_class.keys())[:num_classes]

    for cls in classes:
        random.shuffle(files_for_class[cls])
    files_for_class = {x: files_for_class[x] for x in classes}
    dirs = {}

    for split_name, split_count in splits.items():
        print(split_name, ":")
        split_dir = download_dir / split_name
        split_files, files_for_class = split_class_lists(files_for_class, split_count)
        if not split_dir.exists():
            download_from_zip(zip_url, split_dir, split_files)
        dirs[split_name] = split_dir

    return dirs


def format_frames(frame, output_size):
    frame = tf.image.convert_image_dtype(frame, tf.float32)
    frame = tf.image.resize_with_pad(frame, *output_size)
    return frame


def frames_from_video_file(video_path, n_frames, output_size=(224, 224), frame_step=15):
    result = []
    src = cv2.VideoCapture(str(video_path))
    video_length = src.get(cv2.CAP_PROP_FRAME_COUNT)
    need_length = 1 + (n_frames - 1) * frame_step

    if need_length > video_length:
        start = 0
    else:
        max_start = video_length - need_length
        start = random.randint(0, max_start + 1)
    src.set(cv2.CAP_PROP_POS_FRAMES, start)
    ret, frame = src.read()
    result.append(format_frames(frame, output_size))

    for _ in range(n_frames - 1):
        for _ in range(frame_step):
            ret, frame = src.read()
        if ret:
            frame = format_frames(frame, output_size)
            result.append(frame)
        else:
            result.append(np.zeros_like(result[0]))

    src.release()
    result = np.array(result)[..., [2, 1, 0]]

    return result


def to_gif(images):
    converted_images = np.clip(images * 255, 0, 255).astype(np.uint8)
    imageio.mimsave('./animation.gif', converted_images, duration=10)
    return embed.embed_file('./animation.gif')


class FrameGenerator:
    def __init__(self, path, n_frames, training=False):
        self.path = path
        self.n_frames = n_frames
        self.training = training
        self.class_names = sorted(set(p.name for p in self.path.iterdir() if p.is_dir()))
        self.class_ids_for_name = dict((name, idx) for idx, name in enumerate(self.class_names))

    def get_files_and_class_names(self):
        video_paths = list(self.path.glob('*/*.avi'))
        classes = [p.parent.name for p in video_paths]
        return video_paths, classes

    def __call__(self):
        video_paths, classes = self.get_files_and_class_names()
        pairs = list(zip(video_paths, classes))

        if self.training:
            random.shuffle(pairs)

        for path, name in pairs:
            video_frames = frames_from_video_file(path, self.n_frames)
            label = self.class_ids_for_name[name]
            yield video_frames, label


def main():
    URL = 'https://storage.googleapis.com/thumos14_files/UCF101_videos.zip'

    files = list_files_from_zip_url(URL)
    files = [f for f in files if f.endswith('.avi')]
    print(files[:10])

    NUM_CLASSES = 10
    FILES_PER_CLASS = 50

    files_for_class = get_files_per_class(files)
    classes = list(files_for_class.keys())

    print('Num classes:', len(classes))
    print('Num videos for class[0]:', len(files_for_class[classes[0]]))

    files_subset = select_subset_of_classes(files_for_class, classes[:NUM_CLASSES], FILES_PER_CLASS)
    print(list(files_subset.keys()))

    download_dir = pathlib.Path('./UCF101_subset/')
    subset_paths = download_ucf_101_subset(URL,
                                           num_classes=NUM_CLASSES,
                                           splits={"train": 30, "val": 10, "test": 10},
                                           download_dir=download_dir)

    video_count_train = len(list(download_dir.glob('train/*/*.avi')))
    video_count_val = len(list(download_dir.glob('val/*/*.avi')))
    video_count_test = len(list(download_dir.glob('test/*/*.avi')))
    video_total = video_count_train + video_count_val + video_count_test
    print(f"Total videos: {video_total}")

    video_path = "End_of_a_jam.ogv"
    sample_video = frames_from_video_file(video_path, n_frames=10)
    print(sample_video.shape)

    to_gif(sample_video)
    ucf_sample_video = frames_from_video_file(next(subset_paths['train'].glob('*/*.avi')), 50)
    to_gif(ucf_sample_video)

    fg = FrameGenerator(subset_paths['train'], 10, training=True)
    frames, label = next(fg())

    print(f"Shape: {frames.shape}")
    print(f"Label: {label}")

    output_signature = (tf.TensorSpec(shape=(None, None, None, 3), dtype=tf.float32),
                        tf.TensorSpec(shape=(), dtype=tf.int16))
    train_ds = tf.data.Dataset.from_generator(FrameGenerator(subset_paths['train'], 10, training=True),
                                              output_signature=output_signature)
    for frames, labels in train_ds.take(10):
        print(labels)
    print(os.getcwd())
    print(subset_paths)

    val_ds = tf.data.Dataset.from_generator(FrameGenerator(subset_paths['val'], 10), output_signature=output_signature)
    train_frames, train_labels = next(iter(train_ds))
    print(f'Shape of training set of frames: {train_frames.shape}')
    print(f'Shape of training labels: {train_labels.shape}')

    val_frames, val_labels = next(iter(val_ds))
    print(f'Shape of validation set of frames: {val_frames.shape}')
    print(f'Shape of validation labels: {val_labels.shape}')

    AUTOTUNE = tf.data.AUTOTUNE

    train_ds = train_ds.cache().shuffle(1000).prefetch(buffer_size=AUTOTUNE)
    val_ds = val_ds.cache().shuffle(1000).prefetch(buffer_size=AUTOTUNE)

    train_ds = train_ds.batch(2)
    val_ds = val_ds.batch(2)

    train_frames, train_labels = next(iter(train_ds))
    print(f'Shape of training set of frames: {train_frames.shape}')
    print(f'Shape of training labels: {train_labels.shape}')

    val_frames, val_labels = next(iter(val_ds))
    print(f'Shape of validation set of frames: {val_frames.shape}')
    print(f'Shape of validation labels: {val_labels.shape}')

    net = tf.keras.applications.EfficientNetB0(include_top=False)
    net.trainable = False

    model = tf.keras.Sequential([
        tf.keras.layers.Rescaling(scale=255),
        tf.keras.layers.TimeDistributed(net),
        tf.keras.layers.Dense(10),
        tf.keras.layers.GlobalAveragePooling3D()
    ])

    model.compile(optimizer='adam',
                  loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
                  metrics=['accuracy'])

    model.fit(train_ds,
              epochs=10,
              validation_data=val_ds,
              callbacks=tf.keras.callbacks.EarlyStopping(patience=2, monitor='val_loss'))


if __name__ == '__main__':
    main()
