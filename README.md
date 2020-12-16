# DeepPPPred

## Dependencies
Here is the list of packages required for running the Python code:
```
pandas
torch
keras
numpy
tqdm
gensim
sklearn
nltk
spacy
networkx
en_core_web_sm
```

## How to Run
1. Unzip `sequences_labels.zip` and `word2vec_100_10_5.zip` files located in the `data` directory. 
2. Set the `data_path` to the `data` directory in the `main.py` file.
3. Run the `main.py` file using the following command:

`python -m main`

## Jupyter Notebook
The notebook for the code is also available in the root folder which can be used as an alternative to the `main.py`.

## Citation
If you use this code, please cite the following paper:
```
Pourreza Shahri, Morteza, Katrina Lyon, Julia Schearer, and Indika Kahanda. "DeepPPPred: An Ensemble of BERT, CNN, and RNN for Classifying Co-mentions of Proteins and Phenotypes." bioRxiv (2020).
DOI: https://doi.org/10.1101/2020.09.18.304329
```
