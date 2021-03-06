import h5py
import csv
import numpy as np
import random
import PIL.Image
import logging
#import matplotlib.pyplot as plt
from HTK import HTKFile

from sklearn.metrics import roc_auc_score, roc_curve, auc

import keras
from keras.layers import (Conv2D, Dropout, MaxPooling2D, Dense,
                          GlobalAveragePooling2D, Flatten,
                          BatchNormalization, AveragePooling2D)
from keras.models import Sequential, load_model
from keras.layers.advanced_activations import LeakyReLU
from keras.preprocessing.image import ImageDataGenerator
from keras.losses import (binary_crossentropy, mean_squared_error,
                          mean_absolute_error)
from keras.regularizers import l2

import my_callbacks
from keras.callbacks import ModelCheckpoint
from keras.callbacks import ReduceLROnPlateau
from keras.callbacks import CSVLogger
from keras.callbacks import EarlyStopping


# Logging Config

LOGFILE = 'logs/syslog.log'
logging.basicConfig(filename=LOGFILE,
                        filemode='a',
                        format='%(asctime)s,%(msecs)d %(name)s '
                        '%(levelname)s %(message)s',
                        datefmt='%H:%M:%S',
                        level=logging.DEBUG)

logger = logging.getLogger('Baseline')
logger.info('---------------------------- Program ---------------------------')
################################################
#
#   Global parameters
#
################################################
logger.info('Reading all parameters')

SPECTPATH = 'workingfiles/features_high_temporal/20_10_180_norm/'
LABELPATH = 'labels/'
FILELIST = 'workingfiles/filelists/'

RESULTPATH = 'trained_model/baseline/'
SUBMISSIONFILE = 'predictions_TL_WF_B.csv'
PREDICTIONPATH = 'prediction/'
dataset = ['BirdVox-DCASE-20k.csv', 'ff1010bird.csv', 'warblrb10k.csv']

logfile_name = RESULTPATH + 'logfile_TL_WF_B.log'
checkpoint_model_name = RESULTPATH + 'ckpt_TL_WF_B.h5'
final_model_name = RESULTPATH + 'flmdl_TL_WF_B.h5'
final_weights_name = RESULTPATH + 'weights_TL_WF_B.h5'

BATCH_SIZE = 16
EPOCH_SIZE = 30
AUGMENT_SIZE = 1
with_augmentation = False
# features type : 'npy', 'mfc', 'h5'
features='npy'
model_operation = 'load'
# model_operations : 'new', 'load', 'test'
shape = (1000, 180)
expected_shape = (1000, 180)
input_cnn_shape = (1000, 180, 1)
spect = np.zeros(shape)
label = np.zeros(1)
# Normalization
max_value = 0
min_value = 0

# Callbacks for logging during epochs
reduceLR = ReduceLROnPlateau(factor=0.2, patience=5, min_lr=0.00001)
checkPoint = ModelCheckpoint(filepath = checkpoint_model_name,
                             monitor= 'val_acc', mode = 'max',
                             save_best_only=True)
csvLogger = CSVLogger(logfile_name, separator=',', append=False)




################################################
#
#   Data set selection
#
################################################
logger.info('Data set selection')
# Parameters in this section can be adjusted to select different data sets to train, test, and validate on.
k_VAL_FILE = 'validation_file_path'
k_TEST_FILE = 'test_file_path'
k_TRAIN_FILE = 'train_file_path'
k_VAL_SIZE = 'validate_size'
k_TEST_SIZE = 'test_size'
k_TRAIN_SIZE = 'train_size'
k_CLASS_WEIGHT = 'class_weight'

# Declare the dictionaries to represent the data sets
d_birdVox = {k_VAL_FILE: 'val_B', k_TEST_FILE: 'test_B', k_TRAIN_FILE: 'train_B',
             k_VAL_SIZE: 1000.0, k_TEST_SIZE: 3000.0, k_TRAIN_SIZE: 16000.0,
             k_CLASS_WEIGHT: {0: 0.50,1: 0.50}}
d_warblr = {k_VAL_FILE: 'val_W', k_TEST_FILE: 'test_W', k_TRAIN_FILE: 'train_W',
            k_VAL_SIZE: 400.0, k_TEST_SIZE: 1200.0, k_TRAIN_SIZE: 6400.0,
            k_CLASS_WEIGHT: {0: 0.75, 1: 0.25}}
d_freefield = {k_VAL_FILE: 'val_F', k_TEST_FILE: 'test_F', k_TRAIN_FILE: 'train_F',
               k_VAL_SIZE: 385.0, k_TEST_SIZE: 1153.0, k_TRAIN_SIZE: 6152.0,
               k_CLASS_WEIGHT: {0: 0.25, 1: 0.75}}
d_fold1 = {k_VAL_FILE: 'val_WF', k_TEST_FILE: 'test_WF', k_TRAIN_FILE: 'train_WF',
           k_VAL_SIZE: 785.0, k_TEST_SIZE: 2353.0, k_TRAIN_SIZE: 12552.0,
           k_CLASS_WEIGHT: {0: 0.50, 1: 0.50}}
d_all3 = {k_VAL_FILE: 'val_BWF_short', k_TEST_FILE:'test', k_TRAIN_FILE: 'train_BWF_short',
           k_VAL_SIZE: 1000.0, k_TEST_SIZE: 12620.0, k_TRAIN_SIZE: 16000.0,
           k_CLASS_WEIGHT: {0: 0.50, 1: 0.50}}
d_test = {k_VAL_FILE: 'val_test', k_TEST_FILE:'test_test', k_TRAIN_FILE: 'train_test',
           k_VAL_SIZE: 20.0, k_TEST_SIZE: 20.0, k_TRAIN_SIZE: 45.0,
           k_CLASS_WEIGHT: {0: 0.50, 1: 0.50}}
# Set these variables to change the data set.
training_set = d_birdVox
validation_set = d_birdVox
test_set = d_birdVox

logger.info(f"Dataset -- Training: {training_set}, Validation:"
            "{validation_set}, Test: {test_set}")

# Grab the file lists and sizes from the corresponding data sets.
train_filelist = FILELIST + training_set[k_TRAIN_FILE]
TRAIN_SIZE = training_set[k_TRAIN_SIZE]

val_filelist = FILELIST + validation_set[k_VAL_FILE]
VAL_SIZE = validation_set[k_VAL_SIZE]

test_filelist = FILELIST + test_set[k_TEST_FILE]
TEST_SIZE = test_set[k_TEST_SIZE]

################################################
#
#   Generator with Augmentation
#
################################################

# use this generator when augmentation is needed
def data_generator(filelistpath, batch_size=16, shuffle=False):
    batch_index = 0
    image_index = -1
    filelist = open(filelistpath, 'r')
    filenames = filelist.readlines()
    filelist.close()

    # shuffling filelist
    if shuffle==True:
        random.shuffle(filenames)

    # read labels and save in a dict
    labels_dict = {}
    for n in range(len(dataset)):
        labels_list = csv.reader(open(LABELPATH + dataset[n], 'r'))
        next(labels_list)
        for k, r, v in labels_list:
            labels_dict[r + '/' + k + '.wav'] = v

    while True:
        image_index = (image_index + 1) % len(filenames)

        # if shuffle and image_index = 0
        # shuffling filelist
        if shuffle == True and image_index == 0:
            random.shuffle(filenames)

        file_id = filenames[image_index].rstrip()

        if batch_index == 0:
            # re-initialize spectrogram and label batch
            spect_batch = np.zeros([1, spect.shape[0], spect.shape[1], 1])
            label_batch = np.zeros([1, 1])
            aug_spect_batch = np.zeros([batch_size, spect.shape[0], spect.shape[1], 1])
            aug_label_batch = np.zeros([batch_size, 1])

        # load features with the select format
        if features=='h5':
            hf = h5py.File(SPECTPATH + file_id + '.h5', 'r')
            imagedata = hf.get('features')
            imagedata = np.array(imagedata)
            hf.close()
            imagedata = (imagedata + 15.0966)/(15.0966 + 2.25745)
        elif features == 'npy':
            imagedata = np.load(SPECTPATH + file_id + '.npy')
            if max_value != 0 and min_value != 0:
                imagedata = (imagedata - min_value)/(max_value - min_value)
        elif features == 'mfc':
            htk_reader = HTKFile()
            htk_reader.load(SPECTPATH + file_id[:-4] + '.mfc')
            imagedata = np.array(htk_reader.data)
            imagedata = imagedata / 17.0

        # processing files with shapes other than expected shape in warblr dataset

        if imagedata.shape[0] != expected_shape[0]:
            old_imagedata = imagedata
            imagedata = np.zeros(expected_shape)

            if old_imagedata.shape[0] < expected_shape[0]:

                diff_in_frames = expected_shape[0] - old_imagedata.shape[0]
                if diff_in_frames < expected_shape[0] / 2:
                    imagedata = np.vstack((old_imagedata, old_imagedata[
                        range(old_imagedata.shape[0] - diff_in_frames, old_imagedata.shape[0])]))

                elif diff_in_frames > expected_shape[0] / 2:
                    count = np.floor(expected_shape[0] / old_imagedata.shape[0])
                    remaining_diff = (expected_shape[0] - old_imagedata.shape[0] * int(count))
                    imagedata = np.vstack(([old_imagedata] * int(count)))
                    imagedata = np.vstack(
                        (imagedata, old_imagedata[range(old_imagedata.shape[0] - remaining_diff, old_imagedata.shape[0])]))

            elif old_imagedata.shape[0] > expected_shape[0]:
                diff_in_frames = old_imagedata.shape[0] - expected_shape[0]

                if diff_in_frames < expected_shape[0] / 2:
                    imagedata[range(0, diff_in_frames + 1), :] = np.mean(np.array([old_imagedata[range(0, diff_in_frames + 1), :],old_imagedata[range(old_imagedata.shape[0] - diff_in_frames - 1, old_imagedata.shape[0]), :]]),axis=0)
                    imagedata[range(diff_in_frames + 1, expected_shape[0]), :] = old_imagedata[range(diff_in_frames + 1, expected_shape[0])]

                elif diff_in_frames > expected_shape[0] / 2:
                    count = int(np.floor(old_imagedata.shape[0] / expected_shape[0]))
                    remaining_diff = (old_imagedata.shape[0] - expected_shape[0] * count)
                    for index in range(0, count):
                        imagedata[range(0, expected_shape[0]), :] = np.sum([imagedata, old_imagedata[range(index * expected_shape[0], (index + 1) * expected_shape[0])]],axis=0) / count
                        imagedata[range(0, remaining_diff), :] = np.mean(np.array([old_imagedata[range(old_imagedata.shape[0] - remaining_diff, old_imagedata.shape[0]), :],imagedata[range(0, remaining_diff), :]]), axis=0)


        imagedata = np.reshape(imagedata, (1, imagedata.shape[0], imagedata.shape[1], 1))

        spect_batch[0, :, :, :] = imagedata
        label_batch[0, :] = labels_dict[file_id]

        gen_img = datagen.flow(imagedata, label_batch[0, :], batch_size=1, shuffle=False, save_to_dir=None)
        aug_spect_batch[batch_index, :, :, :] = imagedata
        aug_label_batch[batch_index, :] = label_batch[0, :]
        batch_index += 1

        # create the batch with the features and the labels
        for n in range(AUGMENT_SIZE-1):
            aug_spect_batch[batch_index, :, :, :], aug_label_batch[batch_index, :] = gen_img.next()
            batch_index += 1
            if batch_index >= batch_size:
                batch_index = 0
                inputs = [aug_spect_batch]
                outputs = [aug_label_batch]
                yield inputs, outputs


################################################
#
#   Generator without Augmentation
#
################################################

def dataval_generator(filelistpath, batch_size=32, shuffle=False):
    batch_index = 0
    image_index = -1

    filelist = open(filelistpath, 'r')
    filenames = filelist.readlines()
    filelist.close()


    # read labels and save in a dict
    labels_dict = {}
    labels_dict = {}
    for n in range(len(dataset)):
        labels_list = csv.reader(open(LABELPATH + dataset[n], 'r'))
        next(labels_list)
        for k, r, v in labels_list:
            labels_dict[r + '/' + k + '.wav'] = v

    while True:
        image_index = (image_index + 1) % len(filenames)

        # if shuffle and image_index = 0
        # shuffling filelist
        if shuffle == True and image_index == 0:
            random.shuffle(filenames)

        file_id = filenames[image_index].rstrip()

        if batch_index == 0:
            # re-initialize spectrogram and label batch
            spect_batch = np.zeros([batch_size, spect.shape[0], spect.shape[1], 1])
            label_batch = np.zeros([batch_size, 1])

        # load features with the select format
        if features == 'h5':
            hf = h5py.File(SPECTPATH + file_id + '.h5', 'r')#[:-4]for evaluation dataset
            imagedata = hf.get('features')
            imagedata = np.array(imagedata)
            hf.close()
            imagedata = (imagedata + 15.0966)/(15.0966 + 2.25745)
        elif features == 'npy':
            imagedata = np.load(SPECTPATH + file_id + '.npy')
            if max_value != 0 and min_value != 0:
                imagedata = (imagedata - min_value)/(max_value - min_value)
        elif features == 'mfc':
            htk_reader = HTKFile()
            htk_reader.load(SPECTPATH + file_id[:-4] + '.mfc')
            imagedata = np.array(htk_reader.data)
            imagedata = imagedata/17.0

        # processing files with shapes other than expected shape in warblr dataset
        if imagedata.shape[0] != expected_shape[0]:
            old_imagedata = imagedata
            imagedata = np.zeros(expected_shape)

            if old_imagedata.shape[0] < expected_shape[0]:

                diff_in_frames = expected_shape[0] - old_imagedata.shape[0]
                if diff_in_frames < expected_shape[0] / 2:
                    imagedata = np.vstack((old_imagedata, old_imagedata[
                        range(old_imagedata.shape[0] - diff_in_frames, old_imagedata.shape[0])]))

                elif diff_in_frames > expected_shape[0] / 2:
                    count = np.floor(expected_shape[0] / old_imagedata.shape[0])
                    remaining_diff = (expected_shape[0] - old_imagedata.shape[0] * int(count))
                    imagedata = np.vstack(([old_imagedata] * int(count)))
                    imagedata = np.vstack(
                        (imagedata, old_imagedata[range(old_imagedata.shape[0] - remaining_diff, old_imagedata.shape[0])]))

            elif old_imagedata.shape[0] > expected_shape[0]:
                diff_in_frames = old_imagedata.shape[0] - expected_shape[0]

                if diff_in_frames < expected_shape[0] / 2:
                    imagedata[range(0, diff_in_frames + 1), :] = np.mean(np.array([old_imagedata[range(0, diff_in_frames + 1), :],old_imagedata[range(old_imagedata.shape[0] - diff_in_frames - 1, old_imagedata.shape[0]), :]]),axis=0)
                    imagedata[range(diff_in_frames + 1, expected_shape[0]), :] = old_imagedata[range(diff_in_frames + 1, expected_shape[0])]

                elif diff_in_frames > expected_shape[0] / 2:
                    count = int(np.floor(old_imagedata.shape[0] / expected_shape[0]))
                    remaining_diff = (old_imagedata.shape[0] - expected_shape[0] * count)
                    for index in range(0, count):
                        imagedata[range(0, expected_shape[0]), :] = np.sum([imagedata, old_imagedata[range(index * expected_shape[0], (index + 1) * expected_shape[0])]],axis=0) / count
                        imagedata[range(0, remaining_diff), :] = np.mean(np.array([old_imagedata[range(old_imagedata.shape[0] - remaining_diff, old_imagedata.shape[0]), :],imagedata[range(0, remaining_diff), :]]), axis=0)

        imagedata = np.reshape(imagedata, (1, imagedata.shape[0], imagedata.shape[1], 1))
        spect_batch[batch_index, :, :, :] = imagedata
        if model_operation != 'test':
            label_batch[batch_index, :] = labels_dict[file_id]

        batch_index += 1

        # create the batch with the features and the labels
        if batch_index >= batch_size:
            batch_index = 0
            inputs = [spect_batch]
            outputs = [label_batch]
            yield inputs, outputs

def datatest_generator(filelistpath, batch_size=32, shuffle=False):
    batch_index = 0
    image_index = -1

    filelist = open(filelistpath, 'r')
    filenames = filelist.readlines()
    filelist.close()

    # read labels and save in a dict
    labels_dict = {}
    labels_dict = {}
    for n in range(len(dataset)):
        labels_list = csv.reader(open(LABELPATH + dataset[n], 'r'))
        next(labels_list)
        for k, r, v in labels_list:
            labels_dict[r + '/' + k] = v

    while True:
        image_index = (image_index + 1) % len(filenames)

        # if shuffle and image_index = 0
        # shuffling filelist
        if shuffle == True and image_index == 0:
            random.shuffle(filenames)

        file_id = filenames[image_index].rstrip()

        if batch_index == 0:
            # re-initialize spectrogram and label batch
            spect_batch = np.zeros([batch_size, spect.shape[0], spect.shape[1], 1])
            label_batch = np.zeros([batch_size, 1])

        # load features with the select format
        if features == 'h5':
            hf = h5py.File(SPECTPATH + file_id + '.h5', 'r')#[:-4]for evaluation dataset
            imagedata = hf.get('features')
            imagedata = np.array(imagedata)
            hf.close()
            imagedata = (imagedata + 15.0966)/(15.0966 + 2.25745)
        elif features == 'npy':
            imagedata = np.load(SPECTPATH + file_id + '.npy')
            if max_value != 0 and min_value != 0:
                imagedata = (imagedata - min_value)/(max_value - min_value)
        elif features == 'mfc':
            htk_reader = HTKFile()
            htk_reader.load(SPECTPATH + file_id[:-8] + '.mfc')
            imagedata = np.array(htk_reader.data)
            imagedata = imagedata/17.0

        # processing files with shapes other than expected shape in warblr dataset
        if imagedata.shape[0] != expected_shape[0]:
            old_imagedata = imagedata
            imagedata = np.zeros(expected_shape)

            if old_imagedata.shape[0] < expected_shape[0]:

                diff_in_frames = expected_shape[0] - old_imagedata.shape[0]
                if diff_in_frames < expected_shape[0] / 2:
                    imagedata = np.vstack((old_imagedata, old_imagedata[
                        range(old_imagedata.shape[0] - diff_in_frames, old_imagedata.shape[0])]))

                elif diff_in_frames > expected_shape[0] / 2:
                    count = np.floor(expected_shape[0] / old_imagedata.shape[0])
                    remaining_diff = (expected_shape[0] - old_imagedata.shape[0] * int(count))
                    imagedata = np.vstack(([old_imagedata] * int(count)))
                    imagedata = np.vstack(
                        (imagedata, old_imagedata[range(old_imagedata.shape[0] - remaining_diff, old_imagedata.shape[0])]))

            elif old_imagedata.shape[0] > expected_shape[0]:
                diff_in_frames = old_imagedata.shape[0] - expected_shape[0]

                if diff_in_frames < expected_shape[0] / 2:
                    imagedata[range(0, diff_in_frames + 1), :] = np.mean(np.array([old_imagedata[range(0, diff_in_frames + 1), :],old_imagedata[range(old_imagedata.shape[0] - diff_in_frames - 1, old_imagedata.shape[0]), :]]),axis=0)
                    imagedata[range(diff_in_frames + 1, expected_shape[0]), :] = old_imagedata[range(diff_in_frames + 1, expected_shape[0])]

                elif diff_in_frames > expected_shape[0] / 2:
                    count = int(np.floor(old_imagedata.shape[0] / expected_shape[0]))
                    remaining_diff = (old_imagedata.shape[0] - expected_shape[0] * count)
                    for index in range(0, count):
                        imagedata[range(0, expected_shape[0]), :] = np.sum([imagedata, old_imagedata[range(index * expected_shape[0], (index + 1) * expected_shape[0])]],axis=0) / count
                        imagedata[range(0, remaining_diff), :] = np.mean(np.array([old_imagedata[range(old_imagedata.shape[0] - remaining_diff, old_imagedata.shape[0]), :],imagedata[range(0, remaining_diff), :]]), axis=0)

        imagedata = np.reshape(imagedata, (1, imagedata.shape[0], imagedata.shape[1], 1))

        spect_batch[batch_index, :, :, :] = imagedata

        batch_index += 1

        # create the batch with the features
        if batch_index >= batch_size:
            batch_index = 0
            inputs = [spect_batch]
            yield inputs
################################################

logger.info('Genereting data for Tranning')

if(with_augmentation == True):
    train_generator = data_generator(train_filelist, BATCH_SIZE, True)
else:
    train_generator = dataval_generator(train_filelist, BATCH_SIZE, True)

validation_generator = dataval_generator(val_filelist, BATCH_SIZE, False)
test_generator = datatest_generator(test_filelist, BATCH_SIZE, False)

datagen = ImageDataGenerator(
    featurewise_center=False,
    featurewise_std_normalization=False,
    rotation_range=0,
    width_shift_range=0.05,
    height_shift_range=0.9,
    horizontal_flip=False,
    fill_mode="wrap")

################################################
#
#   Model Creation
#
################################################
if model_operation == 'new':
    logger.info('Creating new Sequential Mode')
    model = Sequential()

    # convolution layers
    model.add(Conv2D(16, (3, 3), padding='valid', input_shape=input_cnn_shape, ))  # low: try different kernel_initializer
    model.add(BatchNormalization())  # explore order of Batchnorm and activation
    model.add(LeakyReLU(alpha=.001))
    model.add(MaxPooling2D(pool_size=(3, 3)))  # experiment with using smaller pooling along frequency axis
    model.add(Conv2D(16, (3, 3), padding='valid'))
    model.add(BatchNormalization())
    model.add(LeakyReLU(alpha=.001))
    model.add(MaxPooling2D(pool_size=(3, 3)))
    model.add(Conv2D(16, (3, 3), padding='valid'))
    model.add(BatchNormalization())
    model.add(LeakyReLU(alpha=.001))
    model.add(MaxPooling2D(pool_size=(3, 1)))
    model.add(Conv2D(16, (3, 3), padding='valid', kernel_regularizer=l2(0.01)))  # drfault 0.01. Try 0.001 and 0.001
    model.add(BatchNormalization())
    model.add(LeakyReLU(alpha=.001))
    model.add(MaxPooling2D(pool_size=(3, 1)))

    # dense layers
    model.add(Flatten())
    model.add(Dropout(0.5))
    model.add(Dense(256))
    model.add(BatchNormalization())
    model.add(LeakyReLU(alpha=.001))
    model.add(Dropout(0.5))
    model.add(Dense(32))
    model.add(BatchNormalization())
    model.add(LeakyReLU(alpha=.001))  # leaky relu value is very small experiment with bigger ones
    model.add(Dropout(0.5))  # experiment with removing this dropout
    model.add(Dense(1, activation='sigmoid'))

# load model and weights from other trainings
elif model_operation == 'load' or model_operation == 'test':
    model = load_model(RESULTPATH + 'flmdl_TF_WF.h5')
    model.load_weights(RESULTPATH + 'weights_TF_WF.h5', by_name=True)

# define the optimizer and compile the model
if model_operation == 'new' or model_operation == 'load':
    adam = keras.optimizers.Adam(lr=0.001, beta_1=0.9, beta_2=0.999, epsilon=None, decay=0.0)
    model.compile(optimizer=adam, loss='binary_crossentropy', metrics=['acc'])

    # prepare callback
    histories = my_callbacks.Histories()

model.summary()
logger.info(model.summary())

my_steps = np.floor(TRAIN_SIZE*AUGMENT_SIZE / BATCH_SIZE)
my_val_steps = np.floor(VAL_SIZE / BATCH_SIZE)
my_test_steps = np.ceil(TEST_SIZE / BATCH_SIZE)

# fit the model and start training
if model_operation == 'new' or model_operation == 'load':
    logger.info('Model fitting')
    history = model.fit_generator(
        train_generator,
        steps_per_epoch=my_steps,
        epochs=EPOCH_SIZE,
        validation_data=validation_generator,
        validation_steps=my_val_steps,
        callbacks= [checkPoint, reduceLR, csvLogger],
        class_weight= training_set[k_CLASS_WEIGHT],
        verbose=True)

    model.save(final_model_name)
    model.save_weights(final_weights_name)
    logger.info('Training done. The results are in :\n'+RESULTPATH)

# Generate the predicitons in the test step
logger.info('Genereting Predictions')
pred_generator = datatest_generator(test_filelist, BATCH_SIZE, False)
y_pred = model.predict_generator(
    pred_generator,
    steps=my_test_steps)

# saving predictions in csv file

testfile = open(test_filelist, 'r')
testfilenames = testfile.readlines()
testfile.close()

HEADER = ['itemid','prediction']

fidwr = open(PREDICTIONPATH+SUBMISSIONFILE, 'wt')
try:
    writer = csv.writer(fidwr)
    writer.writerow(HEADER)
    for i in range(len(testfilenames)):
        strf = testfilenames[i]
        writer.writerow((strf[strf.find('/')+1:-5], float(y_pred[i])))
finally:
    fidwr.close()
