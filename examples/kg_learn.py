# Copyright (c) 2021 OpenKS Authors, DCD Research Lab, Zhejiang University. 
# All Rights Reserved.

import os, argparse
from openks.loaders import loader_config, SourceType, FileType, GraphLoader
from openks.models import OpenKSModel
from py2neo import Graph


def parse_args(args=None):
	parser = argparse.ArgumentParser(
		description='Training and Testing Knowledge Graph Embedding Models',
		usage='train.py [<args>] [-h | --help]'
	)
	parser.add_argument('--model', default='TransE', type=str)
	parser.add_argument('--dataset', default='FB-simple', type=str)
	parser.add_argument('-d', '--hidden_dim', default=1000, type=int)
	parser.add_argument('--epoch', default=150, type=int)
	parser.add_argument('-ef', '--eval_freq', default=50, type=int)
	parser.add_argument('--test_batch_size', default=16, type=int, help='valid/test batch size')
	parser.add_argument('-nrs', '--random_split', action='store_false', default=True)
	parser.add_argument('--split_ratio', default=0.05, type=float)
	parser.add_argument('-de', '--double_entity_embedding', action='store_true')
	parser.add_argument('-dr', '--double_relation_embedding', action='store_true')

	return parser.parse_args(args)


args_from_parse = parse_args()

''' 图谱载入与图谱数据结构生成 '''
# 载入参数配置与数据集载入
loader_config.source_type = SourceType.LOCAL_FILE
loader_config.file_type = FileType.OPENKS
# loader_config.source_type = SourceType.NEO4J
# graph_db = Graph(host='127.0.0.1', http_port=7474, user='neo4j', password='123456')
# loader_config.graph_db = graph_db
# loader_config.source_uris = 'openks/data/company-kg'
# dataset_name = 'FB15k-237'
dataset_name = args_from_parse.dataset
loader_config.source_uris = 'openks/data/'+dataset_name
# loader_config.source_uris = 'openks/data/medical-kg'
loader_config.data_name = 'my-data-set'
# 图谱数据结构载入
graph_loader = GraphLoader(loader_config)
graph = graph_loader.graph
graph.info_display()
''' 图谱表示学习模型训练 '''
# 列出已加载模型
OpenKSModel.list_modules()


# 算法模型选择配置
args = {
	'gpu': False,
	'learning_rate': 0.0001,
	'epoch': 150,
	'batch_size': 1024, 
	'optimizer': 'adam',
	'margin': 4.0,
	'data_dir': loader_config.source_uris,
	'log_steps': 100,
	'test_log_steps': 1000,
	'gamma': 24.0,
	'epsilon': 2.0,
	'negative_sample_size': 256,
	'negative_adversarial_sampling': True,
	'adversarial_temperature': 1.0,
	'cpu_num': 10,
	'warm_up_steps': None,
	'init_checkpoint': None,
	'uni_weight': False,
	'regularization': 0.0,
	'do_valid': True,
	'do_test': True,
	'evaluate_train': True,
	'random_seed': 1
}
platform = 'PyTorch'
executor = 'KGLearn'
model = 'TransE'
model = args_from_parse.model
args['model_name'] = model
args['hidden_size'] = args_from_parse.hidden_dim
args['epoch'] = args_from_parse.epoch
args['eval_freq'] = args_from_parse.eval_freq
args['model_dir'] = 'models/' + model + '_' + dataset_name + '_' + str(args['random_seed'])
args['save_path'] = args['model_dir']
args['market_path'] = 'openks/market/trained_models/' + model + '_' + dataset_name + '.onnx'
args['double_entity_embedding'] = args_from_parse.double_entity_embedding
args['double_relation_embedding'] = args_from_parse.double_relation_embedding
args['random_split'] = args_from_parse.random_split
args['split_ratio'] = args_from_parse.split_ratio
args['test_batch_size'] = args_from_parse.test_batch_size
if not os.path.exists(args['save_path']):
	os.makedirs(args['save_path'])
print("根据配置，使用 {} 框架，{} 执行器训练 {} 模型。".format(platform, executor, model))
print("-----------------------------------------------")
# 模型训练
executor = OpenKSModel.get_module(platform, executor)
kglearn = executor(graph=graph, model=OpenKSModel.get_module(platform, model), args=args)
kglearn.run()
print("-----------------------------------------------")
