import dataclasses as dc
import json
import typing as t

import ignite.contrib.handlers.tensorboard_logger as tbl
import ignite.contrib.handlers.tqdm_logger as tql
import ignite.engine as ie
import numpy as np
import torch.nn as nn
import torch.optim as optim
import torch.optim.lr_scheduler as lrs
import tqdm

import constants as ct
import databunch.databunch as db
import helpers as hp
import options.experiment_options as eo
import specs.maps as sm


class ExperimentLogger(object):
    DEBUG_TAG = '_debug'
    METRIC_TAG = '_metric'

    class _Decorator:
        @staticmethod
        def main_proc_only(func):
            def inner(self, *args, **kwargs):
                if not self.main_proc:
                    return

                return func(self, *args, **kwargs)

            return inner

    def __init__(self, opts: eo.ExperimentOptions, main_proc: bool, train_metrics: str, dev_metrics: str):
        self.opts = opts
        self.main_proc = main_proc
        self.train_metrics = sm.Metrics[train_metrics].value
        self.dev_metrics = sm.Metrics[dev_metrics].value
        self.pbar = self._init_pbar()
        self.tb_logger = self._init_tb_logger()
        self.metrics = {}

    @_Decorator.main_proc_only
    def _init_pbar(self) -> t.Optional[tql.ProgressBar]:
        train_pbar = tql.ProgressBar(persist=True, dynamic_ncols=True)

        return train_pbar

    @_Decorator.main_proc_only
    def _init_tb_logger(self) -> t.Optional[tbl.TensorboardLogger]:
        return tbl.TensorboardLogger(
            log_dir=(ct.WORK_ROOT / self.opts.run_dir / 'logs').as_posix(),
        )

    @_Decorator.main_proc_only
    def attach_pbar(self, engine: ie.Engine):
        self.pbar.attach(engine, 'all')

    @_Decorator.main_proc_only
    def init_handlers(self, trainer: ie.Engine, evaluator: ie.Engine, model: nn.Module, optimizer):
        self.tb_logger.attach(trainer,
                              log_handler=tbl.OutputHandler(
                                  tag='training',
                                  metric_names='all'),
                              event_name=ie.Events.ITERATION_COMPLETED)
        self.tb_logger.attach(trainer,
                              log_handler=tbl.OptimizerParamsHandler(
                                  optimizer,
                                  tag='training'),
                              event_name=ie.Events.ITERATION_COMPLETED)
        self.tb_logger.attach(trainer,
                              log_handler=tbl.OutputHandler(tag='train',
                                                            metric_names='all'),
                              event_name=ie.Events.EPOCH_COMPLETED)
        self.tb_logger.attach(evaluator,
                              log_handler=tbl.OutputHandler(tag='dev',
                                                            metric_names='all',
                                                            global_step_transform=tbl.global_step_from_engine(trainer)),
                              event_name=ie.Events.EPOCH_COMPLETED)

        if self.opts.debug:
            self.tb_logger.attach(trainer, log_handler=tbl.OptimizerParamsHandler(optimizer, tag=self.DEBUG_TAG),
                                  event_name=ie.Events.ITERATION_COMPLETED)
            self.tb_logger.attach(trainer, log_handler=tbl.WeightsHistHandler(model, tag=self.DEBUG_TAG),
                                  event_name=ie.Events.ITERATION_COMPLETED)
            self.tb_logger.attach(trainer, log_handler=tbl.WeightsScalarHandler(model, tag=self.DEBUG_TAG),
                                  event_name=ie.Events.ITERATION_COMPLETED)
            self.tb_logger.attach(trainer, log_handler=tbl.GradsHistHandler(model, tag=self.DEBUG_TAG),
                                  event_name=ie.Events.EPOCH_COMPLETED)
            self.tb_logger.attach(trainer, log_handler=tbl.GradsScalarHandler(model, tag=self.DEBUG_TAG),
                                  event_name=ie.Events.ITERATION_COMPLETED)
            self.tb_logger.attach(trainer, log_handler=tbl.GradsHistHandler(model, tag=self.DEBUG_TAG),
                                  event_name=ie.Events.EPOCH_COMPLETED)

    @_Decorator.main_proc_only
    def init_log(self,
                 data_bunch: db.VideoDataBunch = None,
                 model: nn.Module = None,
                 criterion: nn.Module = None,
                 optimizer: optim.Adam = None,
                 lr_scheduler: lrs.MultiStepLR = None):
        self.print_options()
        if self.opts.debug:
            self.log(str(data_bunch))
            self.log(str(model))
            self.log(str(criterion))
            self.log(str(optimizer))
            self.log(str(lr_scheduler.state_dict() if lr_scheduler else None))

    def print_options(self):
        def inner(opts: t.Any, prefix: str = ''):
            for name, value in opts.items():
                if isinstance(value, dict):
                    p = prefix + f'.{name}' if prefix else f'{name}'
                    inner(value, p)
                else:
                    p = prefix + f'.{name}' if prefix else f'{name}'
                    self.log(f'{p:<50s}{str(value):>50s}')

        self.log(f'{"Field":<50s}{"Value":>50s}')
        self.log(f'{"=" * 49:<50s}{"=" * 49:>50s}')
        inner(dc.asdict(self.opts))

    @_Decorator.main_proc_only
    def log_metrics(self, metrics: t.Dict[str, float]):
        metrics = ' || '.join(f'{key}={value:1.4f}' for key, value in metrics.items())
        self.log(metrics)

    @_Decorator.main_proc_only
    def log_dev_metrics(self, engine: ie.Engine):
        metrics = ' || '.join(f'dev_{key}={value:1.4f}' for key, value in engine.state.metrics.items())
        self.log(metrics)

    @_Decorator.main_proc_only
    def log(self, msg: str):
        tqdm.tqdm.write(msg)

    @_Decorator.main_proc_only
    def persist_run_opts(self):
        with open(str(ct.WORK_ROOT / self.opts.run_dir / 'run.json'), 'w') as file:
            opts = dc.asdict(self.opts)
            hp.path_to_string(opts)
            json.dump(opts, file, indent=True)

    @_Decorator.main_proc_only
    def persist_metrics(self, metrics: t.Dict[str, float], split: str):
        self.metrics.update(metrics)
        with open(str(ct.WORK_ROOT / self.opts.run_dir / split / 'metrics.json'), 'w') as file:
            json.dump(metrics, file, indent=True)

    @_Decorator.main_proc_only
    def persist_outs(self, outs: t.Dict[str, np.ndarray], tsne_ids: np.ndarray, split: str):
        for name, out in outs.items():
            np.save(ct.WORK_ROOT / self.opts.run_dir / split / f'{name}.npy', out, allow_pickle=False)
        np.save(ct.WORK_ROOT / self.opts.run_dir / split / f'tsne_ids.npy', tsne_ids, allow_pickle=False)

    @_Decorator.main_proc_only
    def persist_experiment(self):
        hparams = hp.flatten_dict(dc.asdict(self.opts))
        metrics = {f'{self.METRIC_TAG}/{k}': v for k, v in self.metrics.items()}
        self.tb_logger.writer.add_hparams(hparams, metrics)

    @_Decorator.main_proc_only
    def close(self):
        self.pbar.close()
        self.tb_logger.close()
