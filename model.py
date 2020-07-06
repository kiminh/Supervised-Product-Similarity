#!/usr/bin/env python

import fasttext
import pandas as pd
import numpy as np
import nltk
from nltk.corpus import stopwords
import os

import tensorflow as tf
from tensorflow.keras.layers import LSTM, Dense, Input, Dropout, Lambda, Concatenate

# Have to download the stopwords
# nltk.download('stopwords')

# Get the fasttext model (we are using the largest one they offer [600B tokens])
fasttext_model = fasttext.load_model('models/crawl-300d-2M-subword.bin')


# ## Data Processsing and Organization
# Here, all we really want to do is prepare the data for training. This includes:
# * Simplifying the original data
# * Normalizing the data 
# * Balancing the positive and negative examples
# * Creating the embedding representations that will actually get fed into the neural network


# Organizing and normalizing the data
"""
Essentially, we want to only have three attributes for each training example: title_one, title_two, label
For normalization, we are just going to use the nltk stopwords and punctuation
"""

def preprocessing(orig_data):
    """
    Normalizes the data by getting rid of stopwords and punctuation
    """
    
    # Creates the stopwords
    to_stop = stopwords.words('english')
    punctuation = "!”#$%&’()*+,-./:;<=>?@[\]^_`{|}~ "
    for c in punctuation:
        to_stop.append(c)

    to_stop.append('null')
    
    # The new names of the columns
    column_names = ['title_one', 'title_two', 'label']
    # A new dataframe for the data we are going to be creating
    norm_computers = pd.DataFrame(columns = column_names)
    # Iterate over the original dataframe (I know it is slow and there are probably better ways to do it)
    for row in orig_data.itertuples():
        title_left = row.title_left.split(' ')
        title_right = row.title_right.split(' ')
        
        # Creates a new list of only elements that are not in the stop words
        temp_title_left = []
        for word in title_left:
            if word not in to_stop:
                temp_title_left.append(word)
                
        # Creates a new list of only elements that are not in the stop words
        temp_title_right = []
        for word in title_right:
            if word not in to_stop:
                temp_title_right.append(word)
        
        # Join the elements in the list to create the strings
        title_left = ' '.join(temp_title_left)
        title_right = ' '.join(temp_title_right)
        
        # Append the newly created row (title_left, title_right, label) to the new dataframe
        norm_computers = norm_computers.append(pd.DataFrame([[title_left, title_right, row.label]], columns=column_names))
        
    return norm_computers
        
def create_simple_data():
    """
    Creates and saves a simpler version of the original data that only contains the the two titles and the label.
    """

    # Get the dataset of computer parts
    computers_df = pd.read_json('data/computers_train/computers_train_xlarge_normalized.json.gz',compression='gzip', lines=True)
    norm_computers = preprocessing(computers_df)
    
    # Save the new normalized and simplified data to a CSV file to load later
    norm_computers.to_csv('data/computers_train/computers_train_xlarge_norm_simple.csv', index=False)

# Create and save the data if the simple and normalized data does not exist
if not os.path.exists('data/computers_train/computers_train_xlarge_norm_simple.csv'):
    create_simple_data()

def create_train_df(df):
    """
    Returns a shuffled dataframe with an equal amount of positive and negative examples
    """

    # Get the positive and negative examples
    pos_df = df.loc[df['label'] == 1]
    neg_df = df.loc[df['label'] == 0]
    
    # Shuffle the data
    pos_df = pos_df.sample(frac=1)
    neg_df = neg_df.sample(frac=1)
    
    # Concatenate the positive and negative examples and 
    # make sure there are only as many negative examples as positive examples
    final_df = pd.concat([pos_df, neg_df[:len(pos_df)]])
    
    # Shuffle the final data once again
    final_df.sample(frac=1)
    return final_df

# Create and save the dataframe with equal numbers of positive and negative examples
# and is shuffled
if not os.path.exists('data/computers_train/computers_train_bal_shuffle.csv'):
    # Load the normal simplified data to create the balanced and shuffled data
    computer_df = pd.read_csv('data/computers_train/computers_train_xlarge_norm_simple.csv')
    create_train_df(computer_df).to_csv('data/computers_train/computers_train_bal_shuffle.csv', index=False)

# Load the saved balanced and shuffled data
df = pd.read_csv('data/computers_train/computers_train_bal_shuffle.csv')

##########################################
#Embeddings Creation                     #
#Generates the embeddings and saves them #
##########################################

"""
Definitions of some sizes in the training set
"""
MAX_LEN = 42
EMBEDDING_SHAPE = (300,)
m = 19380
print('MAX_LEN: ' + str(MAX_LEN), 'EMBEDDING_SHAPE: ' + str(EMBEDDING_SHAPE), 'm: ' + str(m))


"""
Create the numpy files of all the training embedddings
We will have two numpy files:
1. The training/validation/test sets
2. The labels
"""

def create_embeddings(df):
    # Create the numpy arrays for storing the embeddings and labels
    total_embeddings = np.zeros(shape=(m, 2, MAX_LEN, EMBEDDING_SHAPE[0]))
    labels = np.zeros(shape=(m))
    
    # I know this is a terrible way of doing this, but iterate over the dataframe
    # and generate the embeddings to add to the numpy array
    for idx, row in enumerate(df.itertuples()):
        for word_idx, word in enumerate(row.title_one.split(' ')):
            total_embeddings[idx, 0, word_idx] = fasttext_model[word]
            
        for word_idx, word in enumerate(row.title_two.split(' ')):
            total_embeddings[idx, 1, word_idx] = fasttext_model[word]
            
        labels[idx] = row.label
        
    return total_embeddings, labels

def save_embeddings(df, embeddings_name, labels_name):
    """
    Saves the embeddings given the embeddings file name and labels file name
    """
    if not os.path.exists('data/computers_numpy/' + embeddings_name + '.npy'):
        embeddings, labels = create_embeddings(df)
        with open('data/computers_numpy/' + embeddings_name + '.npy', 'wb') as f:
            np.save(f, embeddings)

        with open('data/computers_numpy/' + labels_name + '.npy', 'wb') as f:
            np.save(f, labels)

def load_embeddings_and_labels(embeddings_name, labels_name):
    loaded_embeddings = None
    labels = None
    with open('data/computers_numpy/' + embeddings_name + '.npy', 'rb') as f:
        loaded_embeddings = np.load(f)
        loaded_embeddings = np.transpose(loaded_embeddings, (1, 0, 2, 3))
    
    with open('data/computers_numpy/' + labels_name + '.npy', 'rb') as f:
        labels = np.load(f)
    
    return loaded_embeddings, labels

def get_max_len(df):
    max_len = 0
    for row in df.itertuples():
        if len(row.title_one.split(' ')) > max_len:
            max_len = len(row.title_one.split(' '))
            
        if len(row.title_two.split(' ')) > max_len:
            max_len = len(row.title_two.split(' '))
    
    return max_len

# Save the embeddings from the data in the dataframe
save_embeddings(df, 'bal_embeddings', 'bal_labels')

# Load the embeddings and labels from the numpy files
embeddings, labels = load_embeddings_and_labels('bal_embeddings', 'bal_labels')

# Split the data into train, validation and test sets
X_train1 = embeddings[0, :15000]
X_train2 = embeddings[1, :15000]
X_train = np.stack((X_train1, X_train2))
print('Training shape: ' + str(X_train.shape))

X_val1 = embeddings[0, 15000:17000]
X_val2 = embeddings[1, 15000:17000]
X_val = np.stack((X_val1, X_val2))
print('Val shape: ' + str(X_val.shape))

X_test1 = embeddings[0, 17000:]
X_test2 = embeddings[1, 17000:]
X_test = np.stack((X_test1, X_test2))
print('Test shape: ' + str(X_test.shape))

Y_train = labels[:15000]
Y_val = labels[15000:17000]
Y_test = labels[17000:]

def convert_to_one_hot(Y, C):
    """
    Function to create the 
    """
    Y = np.eye(C)[Y.reshape(-1)]
    return Y

Y_train = convert_to_one_hot(Y_train.astype(np.int32), 2)
Y_val = convert_to_one_hot(Y_val.astype(np.int32), 2)
Y_test = convert_to_one_hot(Y_test.astype(np.int32), 2)


# ## Model Info ############################################################################################################################
#                                                                                                                                          #
# For the model, we are going to use LSTMs with a Constrastive Loss Function                                                               #
# that will also be used to predict whether the two products are the same                                                                  #
#                                                                                                                                          #
# First, we have to convert the titles to embeddings through FastText before feeding into the LSTM.                                        #
# The embedding part of this model will not be a layer because:                                                                            #
# * The fasttext model would be time consuming and annoying to get to work with an embedding layer in Keras                                #
# * The fasttext model is not going to be getting its embeddings optimized, so there is really no point in adding it as an embedding layer #
############################################################################################################################################

def square_distance(vectors):
    x, y = vectors
    return tf.square(x - y)

def euclidean_dist_out_shape(shapes):
    # Both inputs are fed in, so just use one of them and get the first value in the shape
    shape1, _ = shapes
    return (shape1[0],)

def siamese_network(input_shape):
    # Defines our inputs
    left_title = Input(input_shape, dtype='float32')
    right_title = Input(input_shape, dtype='float32')
    
    # The LSTM units
    model = tf.keras.Sequential(name='siamese_model')
    model.add(LSTM(units=256, return_sequences=True, name='lstm_1'))
    model.add(Dropout(rate=0.5))
    model.add(LSTM(units=128, return_sequences=True, name='lstm_2'))
    model.add(Dropout(rate=0.5))
    model.add(LSTM(units=128, name='lstm_3'))
    model.add(Dropout(rate=0.5))
    
    # The dense layers
    model.add(Dense(units=1024, activation='elu', name='dense_1'))
    model.add(Dropout(rate=0.5))
    model.add(Dense(units=512, activation='elu', name='dense_2'))
    
    # Forward propagate through the model to generate the encodings
    encoded_left_title = model(left_title)
    encoded_right_title = model(right_title)

    SquareDistanceLayer = Lambda(square_distance)
    distance = SquareDistanceLayer([encoded_left_title, encoded_right_title])
    
    prediction = Dense(units=2, activation='softmax')(distance)

    # Create and return the network
    siamese_net = tf.keras.Model(inputs=[left_title, right_title], outputs=prediction, name='siamese_network')
    return siamese_net

# Note: for the constrastive loss, because 0 denotes that they are from the same class
# and one denotes they are from a different class, I swaped the (Y) and (1 - Y) terms

def constrastive_loss(y_true, y_pred):
    """
    Note: for the constrastive loss, because 0 denotes that they are from the same class
    and one denotes they are from a different class, I swaped the (Y) and (1 - Y) terms
    """
    margin = 2.0
    d = y_pred
    d_sqrt = tf.sqrt(d)
    #tf.print('\nY Pred: ', d, 'Shape: ', tf.shape(d))
    #tf.print('\nY True: ', y_true, 'Shape: ', tf.shape(y_true))
    
    loss = (y_true * d) + ((1 - y_true) * tf.square(tf.maximum(0., margin - d_sqrt)))
    
    #tf.print('\n Constrastive Loss: ', loss, 'Shape: ', tf.shape(loss))
    loss = 0.5 * tf.reduce_mean(loss)
    
    return loss

# Accuracy metric for constrastive loss because values close to 0 are equal and values high are different
# 0.5 is the threshold here
def constrastive_accuracy(y_true, y_pred):
    return tf.reduce_mean(tf.cast(tf.equal(y_true, tf.cast(y_pred < 0.5, y_true.dtype)), y_true.dtype))

def save_model(model, name):
    """
    Saves a model with a particular name
    """
    model.save('models/' + name + '.h5')

model = siamese_network((MAX_LEN, EMBEDDING_SHAPE[0],))
model.summary()

# Compile the model
lr = 0.001
opt = tf.keras.optimizers.Adam(learning_rate=lr)
model.compile(loss='categorical_crossentropy', optimizer='RMSprop', metrics=['accuracy'])

# Train the model
model.fit(x=[X_train1, X_train2], y=Y_train, batch_size=64, epochs=50, validation_data=([X_val[0], X_val[1]], Y_val))

# Test the model
results = model.evaluate([X_test1, X_test2], Y_test, batch_size=16)
print('test loss, test acc: ', results)

# Save the model
model_name = 'Softmax-LSTM-_epochs_loss'
save_model(model, model_name)


# ## Manual Testing ###############################################################
# Converts titles into embeddings arrays and allow the model to make a prediction #
###################################################################################

# Load the model using the weights
model.load_weights('models/' + model_name + '.h5')

title_one = 'True Wireless Earbuds VANKYO X200 Bluetooth 5 0 Earbuds in Ear TWS Stereo Headphones Smart LED Display Charging Case IPX8 Waterproof 120H Playtime Built Mic Deep Bass Sports Work'
title_two = 'TOZO T10 Bluetooth 5 0 Wireless Earbuds Wireless Charging Case IPX8 Waterproof TWS Stereo Headphones Ear Built Mic Headset Premium Sound Deep Bass Sport Black'
title_one_arr = np.zeros((1, 42, 300))
title_two_arr = np.zeros((1, 42, 300))
title_one.lower()
title_two.lower()
for idx, word in enumerate(title_one.split(' ')):
    title_one_arr[0, idx] = fasttext_model[word]
    
for idx, word in enumerate(title_two.split(' ')):
    title_two_arr[0, idx] = fasttext_model[word]

model.predict([title_one_arr, title_two_arr])