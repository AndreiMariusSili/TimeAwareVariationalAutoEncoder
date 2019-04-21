from torch import optim, nn, cuda
from ignite import metrics
import os

from models import options
import pipeline as pipe
from models import i3d
import constants as ct

NUM_DEVICES = cuda.device_count() if cuda.device_count() > 0 else 1

########################################################################################################################
# DATA BUNCH OPTIONS
########################################################################################################################
db_opts = pipe.DataBunchOptions(
    shape='volume',
    frame_size=224
)
########################################################################################################################
# TRAIN DATA
########################################################################################################################
train_do = pipe.DataOptions(
    meta_path=ct.SMTH_META_TRAIN,
    cut=1.0,
    setting='train',
)
train_so = pipe.SamplingOptions(
    num_segments=4,
    segment_size=4
)
train_ds_opts = pipe.DataSetOptions(
    do=train_do,
    so=train_so
)
train_dl_opts = pipe.DataLoaderOptions(
    batch_size=32,
    shuffle=True,
    num_workers=os.cpu_count() // NUM_DEVICES,
    pin_memory=False,
    drop_last=False
)
########################################################################################################################
# VALID DATA
########################################################################################################################
valid_do = pipe.DataOptions(
    meta_path=ct.SMTH_META_VALID,
    cut=1.0,
    setting='valid',
)
valid_so = pipe.SamplingOptions(
    num_segments=4,
    segment_size=4
)
valid_ds_opts = pipe.DataSetOptions(
    do=valid_do,
    so=valid_so
)
valid_dl_opts = pipe.DataLoaderOptions(
    batch_size=32,
    shuffle=False,
    num_workers=os.cpu_count() // NUM_DEVICES,
    pin_memory=False,
    drop_last=False
)
########################################################################################################################
# MODEL AND AUXILIARIES
########################################################################################################################
model_opts = options.I3DOptions(
    num_classes=ct.SMTH_NUM_CLASSES,
)
optimizer_opts = options.AdamOptimizerOptions(
    lr=0.001
)
trainer_opts = options.TrainerOptions(
    epochs=100,
    optimizer=optim.Adam,
    optimizer_opts=optimizer_opts,
    criterion=nn.CrossEntropyLoss
)
evaluator_opts = options.EvaluatorOptions(
    metrics={
        'acc@1': metrics.Accuracy(),
        'acc@2': metrics.TopKCategoricalAccuracy(k=2),
        'loss': metrics.Loss(nn.CrossEntropyLoss())
    }
)
########################################################################################################################
# RUN
########################################################################################################################
dev_i3d_smth = options.RunOptions(
    name='dev_i3d_smth',
    resume=False,
    log_interval=1,
    patience=5,
    model=i3d.I3D,
    model_opts=model_opts,
    data_bunch=pipe.SmthDataBunch,
    db_opts=db_opts,
    train_ds_opts=train_ds_opts,
    valid_ds_opts=valid_ds_opts,
    train_dl_opts=train_dl_opts,
    valid_dl_opts=valid_dl_opts,
    trainer_opts=trainer_opts,
    evaluator_opts=evaluator_opts
)
