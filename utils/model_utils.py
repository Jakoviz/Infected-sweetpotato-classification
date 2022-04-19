from operator import mod
from dotenv import load_dotenv
import os
import time
from utils.time_utils import now_to_str, str_to_datetime, datetime_to_str
from torch import nn
from pathlib import Path
import pandas as pd
import random
import string
import json
from typing import Tuple, Union
from datetime import datetime
import torch
from functools import reduce
from operator import and_

load_dotenv()

DATA_FOLDER = os.getenv("DATA_FOLDER_PATH")
MODEL_FOLDER = os.path.join(DATA_FOLDER, "models")

MODEL_DF = pd.read_csv(os.path.join(DATA_FOLDER, "models.csv"))

AVAILABLE_MODELS = ["resnet18", "inception_v3"]

CLASS_TO_MODEL_NAME_MAPPING = {
	"ResNet": "resnet18",
	"Inception3": "inception_v3",
	"VisionTransformer": "vision_transformer",
}


def get_model_file_name(id: str, model_name: str, timestamp: str) -> str:
	if type(model_name) != str:
		raise ValueError("Model name must be string")

	model_file_name = f"{id}-{model_name}-{timestamp}.pt"
	return model_file_name


def create_model_id_and_timestamp() -> Tuple[str, datetime]:
	id = "".join(
		random.choice(string.ascii_lowercase + string.digits) for i in range(8)
	)
	timestamp = datetime.now()
	return id, timestamp


def split_model_file_name(
	model_file_string: str, return_as_str=False
) -> Tuple[str, str, Union[datetime, str]]:
	if model_file_string.count("-") != 2:
		raise ValueError(
			"model_file_string be in format <id>-<model_name>-<timestamp>.<extension>"
		)

	path = Path(model_file_string)

	# Remove suffix
	path = path.with_suffix("")

	id, model_name, datetime_str = str(path).split("-")

	if return_as_str:
		return id, model_name, datetime_str

	datetime = str_to_datetime(datetime_str)

	return id, model_name, datetime


def save_torch_model(model: nn.Module) -> Tuple[str, str, datetime]:
	# If custom name attribute has been given, use it
	if hasattr(model, "name"):
		model_name = model.name
	# Find class name and determine the model name
	else:
		model_name = type(model).__name__
		model_name = CLASSS_TO_MODEL_NAME_MAPPING[model_name]

	id, timestamp = create_model_id_and_timestamp()
	timestamp_str = datetime_to_str(timestamp)

	model_file_name = get_model_file_name(
		id=id, model_name=model_name, timestamp=timestamp_str
	)
	model_file_path = os.path.join(MODEL_FOLDER, model_file_name)
	torch.save(model.state_dict(), model_file_path)

	return id, model_name, timestamp


def add_model_info_to_df(
	id: str,
	model_name: str,
	# training timestamp
	timestamp=datetime,
	description: str = None,
	# "plant" or "leaf" or some other string
	dataset: str = None,
	num_classes: int = None,
	precision: float = None,
	recall: float = None,
	train_accuracy: float = None,
	train_loss: float = None,
	validation_accuracy: float = None,
	validation_loss: float = None,
	test_accuracy: float = None,
	test_loss: float = None,
	f1_score: float = None,
	other_json: json = None,
):
	if model_name not in AVAILABLE_MODELS:
		raise ValueError(
			f"Model name not recognized, available models: {AVAILABLE_MODELS}"
		)

	if not dataset:
		raise ValueError("Need to specify if model is trained on plants or leaf images")

	if not num_classes:
		raise ValueError("Need to specify how many classes the model recognizes")

	if not test_accuracy or not test_loss or not f1_score:
		raise ValueError("Model should be stored with test results")

	other = json.dumps(other_json)

	pandas_row = [
		id,
		model_name,
		timestamp,
		description,
		dataset,
		num_classes,
		precision,
		recall,
		train_accuracy,
		train_loss,
		validation_accuracy,
		validation_loss,
		test_accuracy,
		test_loss,
		f1_score,
		other,
	]

	MODEL_DF.loc[len(MODEL_DF.index)] = pandas_row
	MODEL_DF.to_csv(os.path.join(DATA_FOLDER, "models.csv"), index=False)


# Helper function to store the model by just passing the model to the function and add relevant results to df
def store_model_and_add_info_to_df(model, **kwargs):
	# Check if the model class inherits PyTorch nn.Module-class so we know if it's PyTorch classifier
	if issubclass(type(model), nn.Module):
		id, model_name, timestamp = save_torch_model(model)
	else:
		raise NotImplementedError(
			"Support for sklearn models has not been implemented yet"
		)

	add_model_info_to_df(id=id, model_name=model_name, timestamp=timestamp, **kwargs)


def get_model_info(id: str) -> pd.Series:
	row = MODEL_DF.loc[MODEL_DF["id"] == id]
	return row


def get_model_info_by_name(name: str, timestamp: datetime) -> pd.Series:
	row = MODEL_DF.loc[
		(MODEL_DF["name"] == name) & (MODEL_DF["timestamp"] == timestamp)
	]
	return row


# You can pass key=value arguments to the function and it returns dataframe row where all conditions are true
def get_model_info_by_attributes(**kwargs) -> pd.Series:
	pandas_filters = []

	# Create all filtered series
	for key, val in kwargs.items():
		filter = MODEL_DF[key] == val
		pandas_filters.append(filter)

	joined_filters = reduce(and_, pandas_filters)

	row = MODEL_DF.loc[joined_filters]
	return row


def get_model_path(id: str) -> str:
	model_info = get_model_info(id)
	model_name = model_info["model_name"].item()
	timestamp = model_info["timestamp"].item()
	timestamp_dt = pd.to_datetime(timestamp)
	timestamp_str = datetime_to_str(timestamp_dt)

	model_file_name = get_model_file_name(
		id=id, model_name=model_name, timestamp=timestamp_str
	)

	model_path = os.path.join(MODEL_FOLDER, model_file_name)

	return model_path
