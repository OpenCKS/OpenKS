# Copyright (c) 2021 OpenKS Authors, DCD Research Lab, Zhejiang University. 
# All Rights Reserved.

import argparse
from openks.models.pytorch import semeval_constant as constant
from openks.loaders import loader_config, SourceType, FileType, Loader
from openks.models import OpenKSModel

''' 文本载入与MMD数据结构生成 '''
# 载入参数配置与数据集载入
loader_config.source_type = SourceType.LOCAL_FILE
loader_config.file_type = FileType.NERO
loader_config.source_uris = 'openks/data/relation-classification-nero'
loader_config.data_name = 'my-data-set'
loader = Loader(loader_config)
dataset = loader.dataset
dataset.info_display()

''' 文本信息抽取模型训练 '''
# 列出已加载模型
OpenKSModel.list_modules()
# 算法模型选择配置

parser = argparse.ArgumentParser(description='NERO args.')


# parser.add_argument("--dataset", type=str, default="nero", help='')
parser.add_argument("--gpu", type=str, default="1", help="The GPU to run on")

parser.add_argument("--target_dir", type=str, default="data", help="")
parser.add_argument("--log_dir", type=str, default="./log/event", help="")
parser.add_argument("--save_dir", type=str, default="./log/model", help="")


# specify the word_embedding_model position and pretrained bert-chinese model folder
parser.add_argument("--word2vec_file", type=str, default="/home/ps/disk_sdb/yyr/codes/NEROtorch/embedding_model/word_embedding_model.model", help="")
parser.add_argument("--bert_pretrained_model", type=str, default="/home/ps/disk_sdb/yyr/codes/NEROtorch/pretrain_models/bert", help="")

# using loader_config.source_uris to replace the following argumnents.
# parser.add_argument("--train_file", type=str, default="./data/supply_cooperate_20210518_data/train.json", help="")
# parser.add_argument("--dev_file", type=str, default="./data/supply_cooperate_20210518_data/test.json", help="")
# parser.add_argument("--test_file", type=str, default="./data/supply_cooperate_20210518_data/test.json", help="")
# parser.add_argument("--pattern_file", type=str, default="./data/supply_cooperate_20210518_data/yanbao_ic_pattern.json", help="")


parser.add_argument("--checkpoint", type=str, default="./checkpoint/model.ckpt", help="")

parser.add_argument("--train_mode", type=str, default="train", help="train or predict")

parser.add_argument("--glove_word_size", type=int, default=int(2.2e6), help="Corpus size for Glove")
parser.add_argument("--glove_dim", type=int, default=300, help="Embedding dimension for Glove")
parser.add_argument("--top_k", type=int, default=100000, help="Finetune top k words in embedding")
parser.add_argument("--length", type=int, default=110, help="Limit length for sentence")
parser.add_argument("--num_class", type=int, default=len(constant.LABEL_TO_ID), help="Number of classes")


parser.add_argument("--gt_batch_size", type=int, default=32, help="Batch size")
parser.add_argument("--pseudo_size", type=int, default=32, help="Batch size for pseudo labeling")
parser.add_argument("--num_epoch", type=int, default=20, help="Number of epochs")
parser.add_argument("--init_lr", type=float, default=0.0001, help="Initial lr")
parser.add_argument("--lr_decay", type=float, default=0.7, help="Decay rate")
parser.add_argument("--keep_prob", type=float, default=0.7, help="Keep prob in dropout")
parser.add_argument("--grad_clip", type=float, default=5.0, help="Global Norm gradient clipping rate")
parser.add_argument("--hidden", type=int, default=150, help="Hidden size")
parser.add_argument("--att_hidden", type=int, default=150, help="Hidden size for attention")

parser.add_argument("--alpha", type=float, default=0.1, help="Weight of pattern RE")
parser.add_argument("--beta", type=float, default=0.2, help="Weight of similarity score")
parser.add_argument("--gamma", type=float, default=0.5, help="Weight of pseudo label")
parser.add_argument("--tau", type=float, default=0.7, help="Weight of tau")
parser.add_argument("--patterns", type=list, default=[], help="pattern list")

args = parser.parse_args()

platform = 'PyTorch'
executor = 'KELearn'
model = 'relation-classification'
print("根据配置，使用 {} 框架，{} 执行器训练 {} 模型。".format(platform, executor, model))
print("-----------------------------------------------")
# 模型训练
executor = OpenKSModel.get_module(platform, executor)
nero = executor(dataset=dataset, model=OpenKSModel.get_module(platform, model), args=args)
nero.run(run_type='relation-classification')

print("-----------------------------------------------")
