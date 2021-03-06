import pandas as pd
import pickle
import torch
from keras.preprocessing.text import Tokenizer
from keras.preprocessing.sequence import pad_sequences
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from tqdm import tqdm, tqdm_notebook
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
import gensim
from sklearn.metrics import f1_score, precision_score, recall_score, confusion_matrix, roc_auc_score
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
from collections import defaultdict
from nltk.data import load
from tqdm import tqdm
import time
from sklearn.model_selection import train_test_split
import warnings
warnings.filterwarnings("ignore")
import os
import nltk
import spacy
import networkx as nx
from sklearn.linear_model import LogisticRegression
nlp = spacy.load("en_core_web_sm")

seed = 0
torch.manual_seed(0)
np.random.seed(1)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

MAX_LEN = 80
SHORT_MAX_LEN = 25
MAX_WORDS = 30000
OOV_TOKEN = 'OOV'
TRUNCATE_MODE = 'post'
PADDING_MODE = 'post'
EMBEDDING_SIZE = 100

class DynamicDataset(Dataset):
    def __init__(self, sequences, features, short_sequences, labels):
        self.sequences = sequences
        self.features = features
        self.short_sequences = short_sequences
        self.labels = labels

    def __getitem__(self, i):
        return (self.sequences[i], self.features[i], self.short_sequences[i], self.labels[i]) 

    def __len__(self):
        return len(self.sequences)

class MultiCnn(nn.Module):
    """
    Defines the CNN model introduced in the paper
    """
    def __init__(self, vocab_size, embedding_size):
        torch.manual_seed(seed)
        super(MultiCnn, self).__init__()
        ### Original Sentence
        self.word_embeddings = nn.Embedding(vocab_size, embedding_size)
        self.word_embeddings.weight.data.copy_(torch.from_numpy(weights_matrix))
        self.conv1 = nn.Conv1d(embedding_size, 64, 3)
        self.drop1 = nn.Dropout(0.5)
        self.max_pool1 = nn.MaxPool1d(2)
        self.flat1 = nn.Flatten()

        self.conv2 = nn.Conv1d(embedding_size, 64, 5)
        self.drop2 = nn.Dropout(0.5)
        self.max_pool2 = nn.MaxPool1d(2)
        self.flat2 = nn.Flatten()
        
        ### Shortest Path
        self.s_word_embeddings = nn.Embedding(vocab_size, embedding_size)
        self.s_word_embeddings.weight.data.copy_(torch.from_numpy(weights_matrix))
        self.s_conv1 = nn.Conv1d(embedding_size, 64, 3)
        self.s_drop1 = nn.Dropout(0.3)
        self.s_max_pool1 = nn.MaxPool1d(2)
        self.s_flat1 = nn.Flatten()

        self.s_conv2 = nn.Conv1d(embedding_size, 64, 5)
        self.s_drop2 = nn.Dropout(0.3)
        self.s_max_pool2 = nn.MaxPool1d(2)
        self.s_flat2 = nn.Flatten()
        
        ### Concatenate
        self.fc1 = nn.Linear(64*98, 100)
        self.drop4 = nn.Dropout(0.2)
        self.fc2 = nn.Linear(100, 64)
        self.drop5 = nn.Dropout(0.2)
        self.fc3 = nn.Linear(64, 1)

    def forward(self, sentence, features, shortest):
        embedding = self.word_embeddings(sentence).permute(0, 2, 1)
        short_embedding = self.s_word_embeddings(shortest).permute(0, 2, 1)
        
        conv1 = F.relu(self.conv1(embedding))
        drop1 = self.drop1(conv1)
        max_pool1 = self.max_pool1(drop1)
        flat1 = self.flat1(max_pool1)
        
        conv2 = F.relu(self.conv2(embedding))
        drop2 = self.drop2(conv2)
        max_pool2 = self.max_pool2(drop2)
        flat2 = self.flat2(max_pool2)
    
        short_conv1 = F.relu(self.s_conv1(short_embedding))
        short_drop1 = self.s_drop1(short_conv1)
        short_max_pool1 = self.s_max_pool1(short_drop1)
        short_flat1 = self.s_flat1(short_max_pool1)
        
        short_conv2 = F.relu(self.s_conv2(short_embedding))
        short_drop2 = self.s_drop2(short_conv2)
        short_max_pool2 = self.s_max_pool2(short_drop2)
        short_flat2 = self.s_flat2(short_max_pool2)
        
        cat = torch.cat((flat1, flat2, short_flat1, short_flat2), dim=1)
        
        fc1 = F.relu(self.fc1(cat.view(len(sentence), -1)))
        drop4 = self.drop4(fc1)
        fc2 = F.relu(self.fc2(drop4))
        drop5 = self.drop5(fc2)
        fc3 = torch.sigmoid(self.fc3(drop5))
        
        return fc3

class BiLSTMShort(nn.Module):
    """
    Defines the RNN model introduced in the paper
    """
    def __init__(self, vocab_size, embedding_size):
        torch.manual_seed(seed)
        super(BiLSTMShort, self).__init__()
        self.word_embeddings = nn.Embedding(vocab_size, embedding_size)
        self.word_embeddings.weight.data.copy_(torch.from_numpy(weights_matrix))
        self.bi_lstm1 = nn.LSTM(embedding_size, 32, bidirectional=True)
        self.bi_lstm2 = nn.LSTM(embedding_size, 32, bidirectional=True)

        self.fc1 = nn.Linear(64*105, 100)
        self.drop1 = nn.Dropout(0.2)
        self.fc2 = nn.Linear(100, 64)
        self.drop2 = nn.Dropout(0.2)
        self.fc3 = nn.Linear(64, 1)

    def forward(self, sentence, features, shortest):
        embedding = self.word_embeddings(sentence)
        short_embedding = self.word_embeddings(shortest)
        lstm_out1, hidden1 = self.bi_lstm1(embedding)
        short_lstm_out1, short_hidden1 = self.bi_lstm2(short_embedding)
        cat = torch.cat((lstm_out1.permute(0, 2, 1), short_lstm_out1.permute(0, 2, 1)), dim=2)
        
        fc1 = F.relu(self.fc1(cat.view(len(sentence), -1)))
        drop1 = self.drop1(fc1)
        fc2 = F.relu(self.fc2(drop1))
        drop2 = self.drop2(fc2)
        fc3 = torch.sigmoid(self.fc3(drop2))
        return fc3


def print_performance(preds, true_labels):
    """
    Print the performance based on the input predictions and true labels
    """
    print('Precision: {0:4.3f}, Recall: {1:4.3f}, F1: {2:4.3f}, AUROC: {3:4.3f}'.format(precision_score(true_labels, preds), recall_score(true_labels, preds), f1_score(true_labels, preds), roc_auc_score(true_labels, preds)))
    print('tn={0:d}, fp={1:d}, fn={2:d}, tp={3:d}'.format(*confusion_matrix(true_labels, preds).ravel()))
    print('{0:4.3f} {1:4.3f} {2:4.3f} {3:4.3f}'.format(precision_score(true_labels, preds), recall_score(true_labels, preds), f1_score(true_labels, preds), roc_auc_score(true_labels, preds)))
    
def train_model(model, dataset, epochs=20, echo=False):
    """
    Trains an input model with an input dataset. 
    epochs is the number of epochs the networks is trained. 
    echo is used to print the loss at the end of each epoch.
    """
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    loader = DataLoader(dataset, batch_size=32)

    # model.train()
    for epoch in range(epochs):
        model.train()
        progress = tqdm_notebook(loader, leave=False) # tqdm_notebook
        for inputs, features, short, target in progress:
            model.zero_grad()
            output = model(inputs.to(device), features.to(device), short.to(device))
            loss = criterion(output, target.to(device))
            loss.backward()
            optimizer.step()
        if echo:
            print(epoch, loss)
    return model

def concatenate_sequences(sequences, features, shorts, labels, added_sequences, added_features, added_shorts, added_labels):
    sequences = torch.cat((sequences, added_sequences))
    features = np.concatenate((features, added_features))
    shorts = np.concatenate((shorts, added_shorts))
    labels = torch.cat((labels, added_labels))
    return sequences, features, shorts, labels

def eval_model(model, dataset, indices=None, return_binary=False, threshold=None):
    """
    Evaluates an input model using an input dataset.
    return_binary is set to True if only binary predictions are required. If False, probabilities are returned.
    """
    if indices is not None:
        dataset = DynamicDataset(dataset[indices][0], dataset[indices][1], dataset[indices][2], dataset[indices][3])
    
    loader = DataLoader(dataset, batch_size=32)
    predictions , true_labels = [], []
    model.eval()
    cnt = 0
    for batch in loader:
        batch = tuple(t.to(device) for t in batch)
        inputs, features, shorts, labels = batch
        with torch.no_grad():
            logits = model(inputs.to(device), features.to(device), shorts.to(device))

        logits = logits.detach().cpu().numpy()
        label_ids = labels.to('cpu').numpy()

        predictions.append(logits)
        true_labels.append(label_ids)
        
        cnt += 1
        if threshold and cnt == threshold:
            break
    
    predictions = [item for sublist in predictions for item in sublist]
    if return_binary:
        predictions = np.array([1 if pred[0] > 0.5 else 0 for pred in predictions])
    labels = [item[0] for sublist in true_labels for item in sublist]
    
    return predictions, labels

def print_stats(dataset):
    print('Length of input dataset: {0:d}'.format(len(dataset)))
    print('Positive instances: {0:d} ({1:4.2f}), Negative instances: {2:d} ({3:4.2f})'.format(sum(dataset.labels == 1)[0], int(sum(dataset.labels == 1)[0]) / len(dataset), sum(dataset.labels == 0)[0], int(sum(dataset.labels == 0)[0]) / len(dataset)))

"""# Experiments"""

def run_model(network):
    """
    Runs a model with pre-defined values.
    """
    model = network(vocab_size+1, EMBEDDING_SIZE)
    model.cuda()
    EPOCHS = 20
    train_model(model, train, epochs=EPOCHS, echo=False)
    return model

if __name__ == '__main__':
    ## Data path required. Set to data if all the data is located in the `data` folder
    data_path = 'data' ## Set the data path here

    ## Load train, validation, and test sets
    train_df = pd.read_csv(os.path.join(data_path, 'train.csv'))
    validation_df = pd.read_csv(os.path.join(data_path, 'validation.csv'))
    test_df = pd.read_csv(os.path.join(data_path, 'test.csv'))

    ## Load pretrained word2vec word embeddings
    pretrained_w2v = gensim.models.Word2Vec.load(os.path.join(data_path, 'word2vec_100_10_5.model'))
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    with open(os.path.join(data_path, 'sequences_labels.pkl'), 'rb') as handle:
        [train_sequences, train_features, train_sp_sequences, train_labels, val_sequences, val_features, val_sp_sequences, val_labels, 
        test_sequences, test_features, test_sp_sequences, test_labels, propheno_sequences, propheno_features, propheno_labels] = pickle.load(handle)

    with open(os.path.join(data_path, 'tokenizer.pkl'), 'rb') as handle:
        tokenizer = pickle.load(handle)

    vocab_size = len(tokenizer.word_index)

    weights_matrix = np.zeros((vocab_size+1, EMBEDDING_SIZE))
    for i, word in enumerate(tokenizer.word_index, start=1):
        try: 
            weights_matrix[i] = pretrained_w2v.wv[word]
        except KeyError:
            weights_matrix[i] = np.random.normal(scale=0.6, size=(EMBEDDING_SIZE, ))

    train = DynamicDataset(train_sequences, train_features, train_sp_sequences, train_labels)
    validation = DynamicDataset(val_sequences, val_features, val_sp_sequences, val_labels)
    test = DynamicDataset(test_sequences, test_features, test_sp_sequences, test_labels)
    
    
    train = DynamicDataset(train_sequences, train_features, train_sp_sequences, train_labels)

    time1 = time.time()
    rnn_model = run_model(BiLSTMShort)
    time2 = time.time()
    print(time2 - time1)
    time1 = time.time()
    cnn_model = run_model(MultiCnn)
    time2 = time.time()
    print(time2 - time1)

    rnn_predictions, true_labels = eval_model(rnn_model, test, return_binary=True)
    print('RNN performance:')
    print_performance(rnn_predictions, true_labels)

    cnn_predictions, true_labels = eval_model(cnn_model, test, return_binary=True)
    print('CNN performance:')
    print_performance(cnn_predictions, true_labels)

    with open(os.path.join(data_path, 'pppred_bert_probabilities_validation_test.pkl'), 'rb') as handle:
        [flat_predictions_val, flat_predictions_test] = pickle.load(handle)

    rnn_val_predictions, true_labels = eval_model(rnn_model, validation, return_binary=False)
    rnn_val_predictions = np.array(rnn_val_predictions)
    cnn_val_predictions, true_labels = eval_model(cnn_model, validation, return_binary=False)
    cnn_val_predictions = np.array(cnn_val_predictions)
    probabilities = clf.predict_proba(vec.transform(validation_df['Sentence']))
    lr = LogisticRegression()
    lr.fit(np.concatenate((rnn_val_predictions, cnn_val_predictions, probabilities[:,1].reshape(-1,1), flat_predictions_val.reshape(-1,1)), axis=1), val_labels)

    rnn_test_predictions, true_labels = eval_model(rnn_model, test, return_binary=False)
    rnn_test_predictions = np.array(rnn_test_predictions)
    cnn_test_predictions, true_labels = eval_model(cnn_model, test, return_binary=False)
    cnn_test_predictions = np.array(cnn_test_predictions)
    probabilities_test = clf.predict_proba(vec.transform(test_df['Sentence']))
    lr_preds = lr.predict(np.concatenate((rnn_test_predictions, cnn_test_predictions, probabilities_test[:,1].reshape(-1,1), flat_predictions_test.reshape(-1,1)), axis=1))
    lr_preds = np.array(lr_preds)
    true_labels = np.array(true_labels)
    print('Ensemble performance:')
    print_performance(lr_preds, true_labels)
