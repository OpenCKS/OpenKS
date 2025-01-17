#   Copyright (c) 2019 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Finetuning on classification tasks."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import

import os
import json
import multiprocessing
import random
import numpy as np
import logging
import time

# NOTE(paddle-dev): All of these flags should be
# set before `import paddle`. Otherwise, it would
# not take any effect.
os.environ['FLAGS_eager_delete_tensor_gb'] = '0'  # enable gc

import paddle.fluid as fluid

from openks.apps.irqa.reader import reader_ce_predict, reader_ce_train
from openks.apps.irqa.model.ernie import ErnieConfig
from openks.apps.irqa.model.cross_encoder_predict import create_predict_model
from openks.apps.irqa.model.cross_encoder_train import create_train_model
from openks.apps.irqa.utils.args import print_arguments, check_cuda, prepare_logger
from openks.apps.irqa.utils.init import init_pretraining_params
from openks.apps.irqa.utils.finetune_args import parser
from openks.apps.irqa.utils.optimization import optimization


class CrossEncoder(object):
    def __init__(self, conf_path, use_cuda=False, device_id=0, batch_size=1, **kwargs):
        if "model_path" in kwargs:
            args = self._parse_args(conf_path, model_path=kwargs["model_path"])
        else:
            args = self._parse_args(conf_path)
        if "model_name" in kwargs:
            args.model_name = kwargs["model_name"].replace('/', '-')
        else:
            args.model_name = "my_ce"
        args.use_cuda = use_cuda
        self.batch_size = batch_size
        self.ernie_config = ErnieConfig(args.ernie_config_path)
        #ernie_config.print_config()

        if use_cuda:
            dev_list = fluid.cuda_places()
            place = dev_list[device_id]
            dev_count = 1
        else:
            place = fluid.CPUPlace()
            dev_count = int(os.environ.get('CPU_NUM', multiprocessing.cpu_count()))
        self.exe = fluid.Executor(place)

        self.predict_reader = reader_ce_predict.CEPredictorReader(
            vocab_path=args.vocab_path,
            label_map_config=args.label_map_config,
            max_seq_len=args.max_seq_len,
            total_num=args.train_data_size,
            do_lower_case=args.do_lower_case,
            in_tokens=args.in_tokens,
            random_seed=args.random_seed,
            tokenizer=args.tokenizer,
            for_cn=args.for_cn,
            task_id=args.task_id)

        """
        self.train_reader = reader_ce_train.CETrainReader(
            vocab_path=args.vocab_path,
            label_map_config=args.label_map_config,
            max_seq_len=args.max_seq_len,
            do_lower_case=args.do_lower_case,
            in_tokens=args.in_tokens,
            random_seed=args.random_seed,
            tokenizer=args.tokenizer,
            for_cn=args.for_cn,
            task_id=args.task_id)
        """

        self.startup_prog = fluid.Program()
        if args.random_seed is not None:
            self.startup_prog.random_seed = args.random_seed

        self.test_prog = fluid.Program()
        with fluid.program_guard(self.test_prog, self.startup_prog):
            with fluid.unique_name.guard():
                self.test_pyreader, self.graph_vars = create_predict_model(
                    args,
                    pyreader_name=args.model_name + '_test_reader',
                    ernie_config=self.ernie_config,
                    is_prediction=True,
                    joint_training=self.joint_training)

        self.test_prog = self.test_prog.clone(for_test=True)

        self.exe = fluid.Executor(place)
        self.exe.run(self.startup_prog)

        if not args.init_checkpoint:
                raise ValueError("args 'init_checkpoint' should be set if"
                                "only doing validation or testing!")
        init_pretraining_params(
            self.exe,
            args.init_checkpoint,
            main_program=self.startup_prog)
        self.args = args


    def _parse_args(self, conf_path, model_path=''):
        args, unknown = parser.parse_known_args()
        with open(conf_path, 'r', encoding='utf8') as json_file:
            config_dict = json.load(json_file)

        args.do_train = False
        args.do_val = False
        args.do_test = True
        args.use_fast_executor = True
        args.max_seq_len = config_dict['max_seq_len']
        args.ernie_config_path = model_path + config_dict['model_conf_path']
        args.vocab_path = model_path + config_dict['model_vocab_path']
        args.init_checkpoint = model_path + config_dict['model_checkpoint_path']

        if "joint_training" in config_dict:
            self.joint_training = config_dict['joint_training']
        else:
            self.joint_training = 0

        return args

    def _parse_train_args(self, conf_path):
        with open(conf_path, 'r', encoding='utf8') as json_file:
            config_dict = json.load(json_file)

            self.args.batch_size = config_dict['batch_size']
            self.args.train_set = config_dict['train_set']
            self.args.save_model_path = config_dict['save_model_path']
            self.args.save_steps = config_dict['save_steps']
            self.args.epoch = config_dict['epoch']
            if 'learning_rate' in config_dict:
                self.args.learning_rate = config_dict['learning_rate']
            else:
                self.args.learning_rate = 2e-5
            if 'log_folder' in config_dict:
                self.args.log_folder = config_dict['log_folder']


    def matching(self, query, para, title=[]):

        assert len(para) == len(query)
        data = []
        if len(title) != 0:
            assert len(para) == len(title)
            for q, t, p in zip(query, title, para):
                data.append(q + '\t' + t + '\t' + p)
        else:
            for q, p in zip(query, para):
                data.append(q + '\t-\t' + p)

        self.test_pyreader.decorate_tensor_provider(
            self.predict_reader.data_generator(
                data,
                batch_size=self.batch_size,
                shuffle=False))

        self.test_pyreader.start()
        fetch_list = [self.graph_vars["probs"].name]
        probs = []

        while True:
            try:
                fetch_result = self.exe.run(program=self.test_prog,
                                            fetch_list=fetch_list)
                np_probs = fetch_result[0]
                if self.joint_training == 0:
                    probs.extend(np_probs[:, 1].reshape(-1).tolist())
                else:
                    probs.extend(np_probs.reshape(-1).tolist())
            except fluid.core.EOFException:
                self.test_pyreader.reset()
                break
        return probs

    def train(self, config_path):
        args = self.args
        self._parse_train_args(config_path)
        print_arguments(args)
        check_cuda(args.use_cuda)
        log = logging.getLogger()

        if self.args.log_folder == '':
            self.args.log_folder = '.'
        if not os.path.exists(self.args.log_folder):
            os.makedirs(self.args.log_folder)
        prepare_logger(log, save_to_file=self.args.log_folder + '/log.train')
        dev_count = 1

        reader = reader_ce_train.CETrainReader(
            vocab_path=args.vocab_path,
            label_map_config=args.label_map_config,
            max_seq_len=args.max_seq_len,
            total_num=args.train_data_size,
            do_lower_case=args.do_lower_case,
            in_tokens=args.in_tokens,
            random_seed=args.random_seed,
            tokenizer=args.tokenizer,
            for_cn=args.for_cn,
            task_id=args.task_id)

        startup_prog = fluid.Program()
        if args.random_seed is not None:
            startup_prog.random_seed = args.random_seed

        train_data_generator = reader.data_generator(
            input_file=args.train_set,
            batch_size=args.batch_size,
            epoch=args.epoch,
            dev_count=dev_count,
            shuffle=True,
            phase="train")

        num_train_examples = reader.get_num_examples(args.train_set)

        if args.in_tokens:
            max_train_steps = args.epoch * num_train_examples // (
                args.batch_size // args.max_seq_len) // dev_count
        else:
            max_train_steps = args.epoch * num_train_examples // args.batch_size // dev_count

        warmup_steps = int(max_train_steps * args.warmup_proportion)
        log.info("Device count: %d" % dev_count)
        log.info("Num train examples: %d" % num_train_examples)
        log.info("Max train steps: %d" % max_train_steps)
        log.info("Num warmup steps: %d" % warmup_steps)

        train_program = fluid.Program()

        with fluid.program_guard(train_program, startup_prog):
            with fluid.unique_name.guard():
                train_pyreader, graph_vars = create_train_model(
                    args,
                    pyreader_name='train_reader',
                    ernie_config=self.ernie_config)
                scheduled_lr = optimization(
                    loss=graph_vars["loss"],
                    warmup_steps=warmup_steps,
                    num_train_steps=max_train_steps,
                    learning_rate=args.learning_rate,
                    train_program=train_program,
                    startup_prog=startup_prog,
                    weight_decay=args.weight_decay,
                    scheduler=args.lr_scheduler,
                    use_dynamic_loss_scaling=args.use_dynamic_loss_scaling,
		            incr_every_n_steps=args.incr_every_n_steps,
		            decr_every_n_nan_or_inf=args.decr_every_n_nan_or_inf,
		            incr_ratio=args.incr_ratio,
		            decr_ratio=args.decr_ratio)

        if args.verbose:
            if args.in_tokens:
                lower_mem, upper_mem, unit = fluid.contrib.memory_usage(
                    program=train_program,
                    batch_size=args.batch_size // args.max_seq_len)
            else:
                lower_mem, upper_mem, unit = fluid.contrib.memory_usage(
                    program=train_program, batch_size=args.batch_size)
            log.info("Theoretical memory usage in training: %.3f - %.3f %s" %
                  (lower_mem, upper_mem, unit))

        nccl2_num_trainers = 1
        nccl2_trainer_id = 0

        self.exe.run(startup_prog)

        init_pretraining_params(
            self.exe,
            args.init_checkpoint,
            main_program=startup_prog)

        """
        exec_strategy = fluid.ExecutionStrategy()
        if args.use_fast_executor:
            exec_strategy.use_experimental_executor = True
        exec_strategy.num_threads = dev_count
        exec_strategy.num_iteration_per_drop_scope = args.num_iteration_per_drop_scope

        train_exe = fluid.ParallelExecutor(
            use_cuda=args.use_cuda,
            loss_name=graph_vars["loss"].name,
            exec_strategy=exec_strategy,
            main_program=train_program,
            num_trainers=nccl2_num_trainers,
            trainer_id=nccl2_trainer_id)
        """

        train_pyreader.decorate_tensor_provider(train_data_generator)
        train_pyreader.start()
        if warmup_steps > 0:
            graph_vars["learning_rate"] = scheduled_lr

        steps = 0
        time_begin = time.time()
        current_epoch = 0
        last_epoch = 0
        total_loss = []
        while True:
            try:
                steps += 1
                if steps % args.skip_steps != 0:
                    self.exe.run(fetch_list=[], program=train_program)
                else:
                    current_example, current_epoch = reader.get_train_progress()
                    time_end = time.time()
                    used_time = time_end - time_begin

                    train_fetch_list = [
                        graph_vars["loss"], graph_vars["accuracy"]
                    ]
                    outputs = self.exe.run(fetch_list=train_fetch_list, program=train_program)
                    tmp_loss = np.mean(outputs[0])
                    tmp_acc = np.mean(outputs[1])
                    total_loss.append(tmp_loss)
                    log.info(
                        "epoch: %d, progress: %d/%d, step: %d, ave loss: %f, "
                        "ave acc: %f, speed: %f steps/s" %
                        (current_epoch, current_example * dev_count, num_train_examples,
                         steps, np.mean(total_loss), tmp_acc,
                         args.skip_steps / used_time))

                    time_begin = time.time()

                if nccl2_trainer_id == 0:
                    if steps % args.save_steps == 0:
                        save_path = os.path.join(args.save_model_path,
                                            "step_" + str(steps))
                        fluid.io.save_persistables(exe, save_path, train_program)

                if last_epoch != current_epoch:
                    last_epoch = current_epoch

            except fluid.core.EOFException:
                save_path = os.path.join(args.save_model_path, "step_" + str(steps))
                fluid.io.save_persistables(self.exe, save_path, train_program)
                train_pyreader.reset()
                break

