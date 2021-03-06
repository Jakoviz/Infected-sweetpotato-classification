import torch
import click
from utils.model_utils import AVAILABLE_MODELS, get_model_info, get_model_info_by_attributes, get_model_path, get_image_size, get_other_json, restore_object
from models.bag_of_words import BagOfWords
from models.model_factory import get_model_class
import logging
from dotenv import load_dotenv
import os
import cv2
import numpy as np
import json
from joblib import load

load_dotenv()
DATA_FOLDER_PATH = os.getenv("DATA_FOLDER_PATH")

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@click.command()
@click.option('-i', '--input', required=True, type=str, help="Path to input image.")
@click.option('-id', '--identifier', type=str, help="Model id. You can print model info with help.py.")
@click.option('-m', '--model', type=click.Choice(AVAILABLE_MODELS, case_sensitive=False), help='Model architechture.')
@click.option('-n', '--num-classes', type=int, help='Number of classes (2 in binary case, 4 in multi-class case).')
@click.option('-d', '--dataset', type=str, help='Name of the dataset model is trained on.')
@click.option('-v', '--verbose', is_flag=True, show_default=True, default=False, help='Print verbose logs.')
def predict(input, identifier, model, num_classes, dataset, verbose):

  if not any([input, identifier, model, num_classes, dataset, verbose]):
      print("""
          Usage: predict.py [OPTIONS]
          Try 'predict.py --help' for help.
      """)

  if verbose:
    logger.setLevel(logging.DEBUG)

  if not identifier and (not all([model, num_classes, dataset])):
    raise ValueError("You must provide either model id or model architechture and num of classes and dataset.")

  logger.info("Loading the model")

  if identifier:
    model_data = get_model_info(id=identifier)
    model_name = model_data['model_name'].item()
    num_classes = model_data['num_classes'].item()
    model = get_model_class(name=model_name, num_of_classes=num_classes)
    model_path = get_model_path(identifier)
    model_id = identifier
  else:
    model_name = model
    model_data = get_model_info_by_attributes(model_name=model, num_classes=num_classes, dataset=dataset)
    if len(model_data) == 0:
      raise ValueError(f"Could not find any model with attributes model name: {model}, num_classes: {num_classes}, dataset: {dataset}. Please check that model with these values exists in models.csv")
    elif len(model_data) > 1:
      best_model = model_data.nlargest(1, columns=['f1_score'])
      model_id = best_model['id'].item()
      model = get_model_class(name=model, num_of_classes=num_classes)
      model_path = get_model_path(model_id)
    else:
      model_id = model_data['id'].item()
      model = get_model_class(name=model, num_of_classes=num_classes)
      model_path = get_model_path(model_id)

    logger.debug(f"Using the model with id: {model_id}")

  # Preprocess image

  logger.info("Preprocessing the image")

  LABELS = json.loads(model_data['other_json'].item())['LABELS']
  CROP_SIZE = get_image_size(model_name)

  image = cv2.imread(input)
  image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
  image = cv2.resize(image, CROP_SIZE)

  if model_name == 'bag_of_words':
    model = load(model_path)
    other_json = get_other_json(model_id)
    feature_detection = other_json['feature_detection']
    k = other_json['k']
    voc = restore_object(other_json['voc'])
    stdslr = restore_object(other_json['standard_scaler'])

    probabilities = BagOfWords.predict_single_image(image, model, feature_detection, k, voc, stdslr)

    results = dict(zip(LABELS, probabilities))
  else:
    device = "cuda" if torch.cuda.is_available() else "cpu"

    model.load_state_dict(torch.load(model_path))
    model = model.to(device)
    model.eval()

    # Convert pixel values to floats between 0 and 1
    image = image.astype("float32") / 255.0

    # Calculate values for mean and std for each channel for normalization
    mean = np.mean(image, axis=(0,1))
    std = np.std(image, axis=(0,1))

    image -= mean
    image /= std

    # Change numpy array from (width, height, channels) to (batch size, channels, width, height)
    image = np.transpose(image, (2, 0, 1))
    image = np.expand_dims(image, 0)

    image = torch.from_numpy(image)

    image = image.to(device)

    logits = model(image)
    probabilities = torch.nn.Softmax(dim=-1)(logits).tolist()[0]

    results = dict(zip(LABELS, probabilities))
  print(results)
  return results

if __name__ == "__main__":
    predict()
