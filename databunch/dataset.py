import typing as t

import imgaug.augmenters as ia
import numpy as np
import pandas as pd
import torch as th
import torch.utils.data as thd
import torchvision.transforms.functional as F  # noqa

import constants as ct
import databunch.label as pil
import databunch.video as piv
import databunch.video_meta as pim
import helpers as hp
import options.data_options as do


def init_worker(_id: int):
    np.random.seed(_id)


def collate(batch: [(piv.Video, pil.Label)]) -> (th.Tensor, th.Tensor, piv.Video, pil.Label):
    videos, labels = zip(*batch)

    videos_data = th.stack([th.stack(video.data, dim=0) for video in videos], dim=0)
    labels_data = th.tensor([label.data for label in labels], dtype=th.int64)

    return videos_data, labels_data, videos, labels


class VideoDataset(thd.Dataset):
    def __init__(self, cut: float, frame_size: int, data_opts: do.DataSetOptions, sampling_opts: do.SamplingOptions):
        """Initialize a video dataset from the DataFrame containing meta information."""
        assert 0.0 <= cut <= 1.0, f'Cut should be between 0.0, and 1.0. Received: {cut}.'
        assert data_opts.setting in ['train', 'eval'], f'Unknown setting: {data_opts.setting}.'

        self.cut = cut
        self.frame_size = frame_size
        self.do = data_opts
        self.so = sampling_opts

        self.meta = hp.read_meta(data_opts.meta_path)
        self.lids = self.meta['lid'].unique()
        self.lid2labels = self.meta.groupby('lid')['label'].head(1)
        self.labels2lid = self.lid2labels.reset_index().set_index('label')

        if data_opts.keep is not None:
            if 0 <= data_opts.keep < 1:
                self._stratified_sample_meta(data_opts.keep)
            else:
                self.meta = self.meta.iloc[0:data_opts.keep]
        self.aug_seq = self._compose_aug_seq()

    def _compose_aug_seq(self) -> ia.Sequential:
        if self.do.setting == 'train':
            aug_seq = ia.Sequential([
                ia.PadToFixedSize(224, 224),
                ia.CropToFixedSize(224, 224),
                ia.Fliplr(0.5),
                ia.Flipud(0.5),
                ia.Add((-25, 25)),
                ia.AddToHueAndSaturation((-25, 25)),
            ])
        else:
            aug_seq = ia.Sequential([
                ia.PadToFixedSize(224, 224, position='center'),
                ia.CropToFixedSize(224, 224, position='center'),
            ])

        return aug_seq

    def aug(self, video_data: t.List[np.ndarray]) -> t.List[th.Tensor]:
        det_aug_seq = self.aug_seq.to_deterministic()

        return [F.to_tensor(det_aug_seq.augment_image(frame_data)) for frame_data in video_data]

    def __getitem__(self, item: int) -> t.Tuple[piv.Video, pil.Label]:
        video_meta = pim.VideoMeta(**self.meta.iloc[item][pim.VideoMeta.fields].to_dict())

        video = piv.Video(video_meta, ct.WORK_ROOT / self.do.root_path, self.do.read_jpeg,
                          self.cut, self.do.setting, self.so.num_segments)
        label = pil.Label(video_meta)

        video.data = self.aug(video.data)

        return video, label

    def get_batch(self, n: int) -> t.Tuple[t.List[piv.Video], t.List[pil.Label]]:
        videos, labels = [], []
        for i, row in self.meta.sample(n=n).iterrows():
            iloc = self.meta.index.get_loc(i)
            video, label = self[iloc]
            videos.append(video)
            labels.append(label)

        return videos, labels

    def __len__(self):
        return len(self.meta)

    def __str__(self):
        string = f"""Something-Something Dataset: {len(self)} x {self[0]}"""

        return string

    def _stratified_sample_meta(self, keep: float):
        """Selects the first instances of a class up to a proportion keep."""
        samples = []
        for lid in self.meta['lid'].unique():
            class_meta = self.meta[self.meta['lid'] == lid]
            cut_off = round(len(class_meta) * keep)
            class_meta_sample = class_meta.iloc[0:cut_off]
            samples.append(class_meta_sample)

        self.meta = pd.concat(samples, verify_integrity=True)
