import os
import re
from dotenv import load_dotenv
import click
import logging
import pandas as pd
from preprocessing.preprocess_split_data import condition_to_label
from segmentation.separate_leaves import segment as segment_leaves
from segmentation.separate_to_plants import segment_plant
from preprocessing.preprocess_leaf_data import preprocess_leaf_data
from segmentation.segmentation_utils import get_masked_image_filename, get_original_image_filename
from utils.path_utils import get_relative_path_to_data_folder
from pprint import pprint

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

load_dotenv()
DATA_FOLDER_PATH = os.getenv('DATA_FOLDER_PATH')
DEFAULT_LEAF_OUTPUT_PATH = os.path.join(DATA_FOLDER_PATH, 'segmented_leaves')
DEFAULT_PLANT_OUTPUT_PATH = os.path.join(DATA_FOLDER_PATH, 'segmented_plants')

@click.command()
@click.option('-e', '--excel-path', type=str, help='Full file path to the Excel-file.')
@click.option('-t', '--type', required=True, type=click.Choice(['plant', 'leaf'], case_sensitive=False), help='Whether the given image data is images of plants or leaves.')
@click.option('-o', '--output-path', type=str, help=f'Folder where the resulting csv and segmented images will be placed. By default they are placed in {DEFAULT_LEAF_OUTPUT_PATH} for leaves and in {DEFAULT_PLANT_OUTPUT_PATH} for plants')
@click.option('-v', '--verbose', is_flag=True, show_default=True, default=False, help='Print verbose logs.')
def segment(excel_path, type, output_path, verbose):
    if verbose:
        logger.setLevel(logging.DEBUG)

    if type == 'plant':
        path_to_csv, path_to_images = segment_plant_data(excel_path, output_path)
    elif type == 'leaf':
        path_to_csv, path_to_images = segment_leaf_data(excel_path, output_path)
    else:
        raise ValueError('Unknown value for flag --type, accepted values are "plant" and "leaf".')

    logger.info('Segmentation finished!')
    logger.info(f'A csv of the segmented data can be found from {path_to_csv}')
    logger.info(f'Segmented images can be found from {path_to_images}')

def segment_plant_data(excel_path, output_path):

    if output_path is None:
        output_path = DEFAULT_PLANT_OUTPUT_PATH

    original_df = pd.read_excel(excel_path)
    # Reset index so we can be sure index runs though from 1 to n
    original_df.reset_index(inplace=True)

    # To check if segmentation produces a right number of images
    segmented_image_value_counts = original_df['Masked image path'].value_counts()

    logger.debug('Creating a dataframe for segmented image data')

    segmented_df = pd.DataFrame(columns=['Genotype', 'Condition', 'Split masked image path', 'Split original image path'])

    logger.info('Segmenting plant images')

    # Store masked_image_path : number of found plants pairs in the dict
    image_path_to_plant_number_map = {}
    falsely_segmented_images = []

    for index, row in original_df.iterrows():
        original_image_path = os.path.join(DATA_FOLDER_PATH, row['Original image path'])        
        masked_image_path = os.path.join(DATA_FOLDER_PATH, row['Masked image path'])
        genotype = row['Genotype']
        condition = row['Condition']
        # Integer distance between the index + 1
        plant_index = abs(index - original_df[original_df['Original image path'] == original_image_path].head(1).index.item()) + 1

        # Segment images if they have not been segmented already
        if masked_image_path not in image_path_to_plant_number_map.keys():
            logger.debug(f"Segmenting file {masked_image_path}")
            segmented_masked_paths, segmented_original_paths = segment_plant(masked_image_path, original_image_path, output_path)

            image_path_to_plant_number_map[masked_image_path] = len(segmented_masked_paths)

            # Segmentation produced wrong number of results
            if len(segmented_masked_paths) != segmented_image_value_counts[row['Masked image path']]:
                # Store falsely segmented output folder
                output_folder = os.path.join(output_path, re.findall(r'[^\/]+(?=\.)', masked_image_path)[0])
                falsely_segmented_images.append(output_folder)


        # If segmentation succeeded
        if image_path_to_plant_number_map[masked_image_path] == segmented_image_value_counts[row['Masked image path']]:
            masked_segmented_path = get_masked_image_filename(masked_image_path, output_path, plant_index)
            original_segmented_path = get_original_image_filename(original_image_path, output_path, plant_index)
        else:
            masked_segmented_path = get_masked_image_filename(masked_image_path, output_path)
            original_segmented_path = get_original_image_filename(original_image_path, output_path)

        new_row = pd.DataFrame(data = {
                'Genotype': [genotype],
                'Condition': [condition],
                'Split masked image path': [masked_segmented_path],
                'Split original image path': [original_segmented_path],
        })

        segmented_df = pd.concat([segmented_df, new_row], ignore_index=True)


    segmented_df = condition_to_label(segmented_df)

    file_name = 'segmented_plants.csv'
    file_path = os.path.join(output_path, file_name)
    logger.debug(f'Writing segmentation results to {file_path}')
    segmented_df.to_csv(file_path, index=False)

    print(f"Incorrectly segmented folders:")
    pprint(falsely_segmented_images)

    return file_path, output_path

def segment_leaf_data(excel_path, output_path):

    if output_path is None:
        output_path = DEFAULT_LEAF_OUTPUT_PATH

    original_df = pd.read_excel(excel_path)

    # To check if segmentation produces a right number of images
    segmented_image_value_counts = original_df['Masked image path'].value_counts()

    logger.debug('Creating a dataframe for segmented image data')
    segmented_df = pd.DataFrame(columns=['Genotype', 'Condition', 'Split masked image path', 'Split original image path'])

    logger.info('Segmenting leaf images')

    # Store masked_image_path : number of found plants pairs in the dict
    image_path_to_plant_number_map = {}
    falsely_segmented_images = set()

    for index, row in original_df.iterrows():
        original_image_path = os.path.join(DATA_FOLDER_PATH, row['Original image path'])
        masked_image_path = os.path.join(DATA_FOLDER_PATH, row['Masked image path'])

        logger.debug(f"Segmenting file {masked_image_path}")

        segmented_masked_paths, segmented_original_paths = segment_leaves(masked_image_path, original_image_path, output_path)

        if masked_image_path not in image_path_to_plant_number_map:
            image_path_to_plant_number_map[masked_image_path] = len(segmented_masked_paths)

        if image_path_to_plant_number_map[masked_image_path] != segmented_image_value_counts[row['Masked image path']]:
            falsely_segmented_images.add(masked_image_path)

        for i in range(len(segmented_masked_paths)):
            segmented_row = pd.DataFrame(data = {
                'Genotype': [row['Genotype']],
                'Condition': [row['Condition']],
                'Split masked image path': [get_relative_path_to_data_folder(segmented_masked_paths[i])],
                'Split original image path': [get_relative_path_to_data_folder(segmented_original_paths[i])],
            })
            segmented_df = pd.concat([segmented_df, segmented_row], ignore_index=True)

    segmented_df = condition_to_label(segmented_df)

    file_name = 'segmented_leaves.csv'
    file_path = os.path.join(output_path, file_name)
    logger.debug(f'Writing segmentation results to {file_path}')
    segmented_df.to_csv(file_path, index=False)

    print(f"Incorrectly segmented folders:")
    pprint(list(falsely_segmented_images))

    return file_path, output_path

if __name__ == '__main__':
    segment()
