"""
File: task_a_evaluate_image_to_text_retrieval.py
Authors: Juan A. Rodriguez , Igor Ugarte, Francesc Net, David Serrano
Description:
    - This script is used to evaluate the image to text retrieval system for task a.
    - It uses the test set for retrieval using KNN
    - Quantitative and qualitative results are presented
"""

import json
import os.path
import pickle
from os import path

import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.neighbors import KNeighborsClassifier

from datasets import Flickr30k
from models_v2 import ResnetFlickr, EmbeddingTextNet, TripletTextImage, EmbeddingImageNet
from evaluation_metrics import mapk
import faiss
cuda = torch.cuda.is_available()


def extract_embeddings(dataloader, model, out_size=256, model_id='', num_samples=10):
    model.to('cuda')
    with torch.no_grad():
        model.eval()
        image_embeddings = np.zeros((num_samples, 1024))
        text_embeddings = np.zeros((num_samples * 5, 1024))
        k = 0
        for images, texts in dataloader:
            images = images[:num_samples, :]
            texts = texts[:num_samples, :]
            if cuda:
                images = images.cuda()
                texts = texts.cuda()
            text_batch = texts.reshape(len(texts) * 5, 300)
            im_emb, text_emb = model.get_embedding_pair(images, text_batch)
            image_embeddings[k:k + len(images)] = im_emb.data.cpu().numpy()
            text_embeddings[k:k + len(texts) * 5] = text_emb.data.cpu().numpy()
            k += len(images)

    return image_embeddings, text_embeddings


def main():
    # Load the datasets
    ROOT_PATH = "../../data/"
    TEST_IMG_EMB = ROOT_PATH + "Flickr30k/test_FasterRCNN_features.pkl"
    TEST_TEXT_EMB = ROOT_PATH + "Flickr30k/test_fasttext_features.pkl"

    # Method selection
    base = 'TextToImage'
    text_aggregation = 'mean'
    image_features = 'FasterRCNN'
    emb_size = 300
    out_size = 4096
    input_size = 1024
    info = 'out_size_' + str(out_size)
    model_id = base + '_' + image_features + '_' + text_aggregation + '_textagg_' + info

    PATH_MODEL = 'models/'

    # Load the test dataset
    test_dataset = Flickr30k(TEST_IMG_EMB, TEST_TEXT_EMB, train=False,
                             text_aggregation=text_aggregation)  # Create the test dataset

    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=test_dataset.length_dataset, shuffle=False,
                                              num_workers=1)

    margin = 1.
    embedding_text_net = EmbeddingTextNet(embedding_size=emb_size, output_size=out_size, sequence_modeling=None)
    embedding_image_net = EmbeddingImageNet(input_size=input_size, output_size=out_size)
    model = TripletTextImage(embedding_text_net, embedding_image_net, margin=margin)

    # Check if file exists
    if path.exists(PATH_MODEL + model_id + '.pth'):
        print('Loading the model from the disk, {}'.format(model_id + '.pth'))
        checkpoint = torch.load(PATH_MODEL + model_id + '.pth')
        model.load_state_dict(checkpoint['model_state_dict'])

    # Obtain ground truth from the json file (test.json)
    with open(ROOT_PATH + 'Flickr30k/test.json') as f:
        data = json.load(f)

    num_samples = 1000  # Number of samples to evaluate
    data = data[:num_samples]

    gt = {}  # Ground truth as a dictionary with the image filename as key and the list of text id as value
    dict_sentences = {}  # Dictionary with the text id as key and the sentence as value
    count = 0
    for item in data:
        gt[item['filename']] = [x['raw'] for x in item['sentences']]
        for sentence in item['sentences']:
            dict_sentences[count] = sentence['raw']
            count += 1

    # Extract embeddings
    image_embeddings, text_embeddings = extract_embeddings(test_loader, model, out_size, model_id, num_samples)

    # Compute the labels for each embedding
    image_labels = [i for i in range(1, len(data) + 1)]
    text_labels = [j for j in range(1, len(data) + 1) for i in range(5)]  # Trick to obtain the same
    # number of labels, copying the same labels 5 (5 text embeddings)

    # Compute the nearest neighbors
    print('Computing the nearest neighbors...')
    k = 5  # Number of nearest neighbors

    index = faiss.IndexFlatL2(image_embeddings.shape[1])  # Build the index
    # add the features of the train set to the index
    index.add(np.float32(image_embeddings))
    # retrieve the features of the test set
    text_embeddings = np.float32(text_embeddings)
    D, I = index.search(np.array(text_embeddings), k)

    # knn = KNeighborsClassifier(n_neighbors=k, algorithm='auto', metric='euclidean').fit(image_embeddings, image_labels)
    #
    # # Make predictions
    # distances, indices = knn.kneighbors(text_embeddings)

    # Compute mAPk
    image_labels_pred = []

    #
    for k_predictions in I.tolist():
        # map indices with the corresponding labels
        k_labels_pred = [image_labels[i] for i in k_predictions]
        image_labels_pred.append(k_labels_pred)

    t_labels = [[i] for i in text_labels]  # Convert list of labels into list of list (for mapk function)
    map_k = mapk(t_labels, image_labels_pred, k=k)
    print(f'mAP@{k}: {map_k}')

    # Qualitative results
    num_samples = 20
    # Create random samples
    random_samples = np.random.choice(list(range(len(data) * 5)), num_samples, replace=False)

    # im_labels, image_labels_pred
    for sample in random_samples:
        print("Example:" + str(sample))
        print("--------------------------------")

        print("Query text: " + dict_sentences[sample])

        # Obtain ground truth image, mapping the text sample to the image id
        gt_image_id = text_labels[sample]
        # Map the id to the image filename
        gt_image_filename = list(gt)[gt_image_id - 1]
        plt.figure(figsize=(15, 10))
        # Plot the ground truth image
        plt.subplot(1, k + 1, 1)
        plt.imshow(plt.imread(ROOT_PATH + 'Flickr30k/flickr30k-images/' + gt_image_filename))

        # Get predicted images from that text
        predictions = I[sample]
        count = 1
        for pred in predictions:
            filename = list(gt)[pred]
            plt.subplot(1, k + 1, count + 1)
            plt.imshow(plt.imread(ROOT_PATH + 'Flickr30k/flickr30k-images/' + filename))
            count += 1
        plt.show()
        print("--------------------------------------------------------------------------------")


# Main
if __name__ == '__main__':
    main()
