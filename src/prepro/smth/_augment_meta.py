from typing import Tuple, List, Any
import pandas as pd
import skvideo.io

from env import logging
import constants as ct
import helpers as hp


def add_columns(meta: pd.DataFrame) -> None:
    """Add columns of interest to the DataFrame."""
    meta['path'] = None
    meta['length'] = None
    meta['height'] = None
    meta['width'] = None
    meta['framerate'] = None
    meta['template_id'] = None


def _augment_row(row: pd.Series) -> pd.Series:
    """Add video and label information to the row."""
    path = ct.SMTH_VIDEO_DIR / f'{row["id"]}.webm'
    row['path'] = path.as_posix()

    video_meta = skvideo.io.ffprobe(path.as_posix())['video']
    row['height'] = int(video_meta['@height'])
    row['width'] = int(video_meta['@width'])
    row['framerate'] = int(video_meta['@avg_frame_rate'].split('/')[0])

    video = skvideo.io.vread(path.as_posix())
    length, _, _, _ = video.shape
    row['length'] = length

    labels2id = hp.read_smth_labels2id(ct.SMTH_LABELS2ID)
    row['template_id'] = labels2id[labels2id['template'] == row['template']]['id'].item()

    return row


def _augment_meta(batch: Tuple[int, List[Any]]) -> hp.parallel.Result:
    """Create a batch of augmented rows."""
    no, batch = batch

    rows = []
    for index, row in batch:
        rows.append((index, _augment_row(row)))

    return hp.parallel.Result(len(batch), rows)


def main():
    logging.info(f'Augmenting metadata for the {ct.SETTING} set...')
    for path in [ct.SMTH_META_TRAIN, ct.SMTH_META_VALID]:
        meta = hp.read_smth_meta(path)
        add_columns(meta)
        for index, row in hp.parallel.execute(_augment_meta, list(meta.iterrows()), 1):
            meta.loc[index] = row
        meta.to_json(path, orient='records')
    logging.info('...Done')