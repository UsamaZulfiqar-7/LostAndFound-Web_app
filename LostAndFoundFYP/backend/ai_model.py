import numpy as np
import os
from tensorflow.keras.applications.resnet50 import ResNet50, preprocess_input
from tensorflow.keras.preprocessing import image
from tensorflow.keras.models import Model
from sklearn.metrics.pairwise import cosine_similarity

# Load pretrained ResNet50 without top layer
base_model = ResNet50(weights="imagenet")
model = Model(inputs=base_model.input,
              outputs=base_model.layers[-2].output)  # 2048 feature vector

UPLOAD_FOLDER = "static/uploads"

def extract_features(img_path):
    img = image.load_img(img_path, target_size=(224, 224))
    img_array = image.img_to_array(img)
    img_array = np.expand_dims(img_array, axis=0)
    img_array = preprocess_input(img_array)

    features = model.predict(img_array, verbose=0)
    return features.flatten()

def find_best_match(found_image_filename, lost_items):
    """
    lost_items = list of objects containing:
        id
        item_name
        image
    """

    found_path = os.path.join(UPLOAD_FOLDER, found_image_filename)

    if not os.path.exists(found_path):
        return None, 0

    found_features = extract_features(found_path)

    best_similarity = 0
    best_item = None

    for item in lost_items:

        if not item.image:
            continue

        lost_path = os.path.join(UPLOAD_FOLDER, item.image)

        if not os.path.exists(lost_path):
            continue

        lost_features = extract_features(lost_path)

        similarity = cosine_similarity(
            [found_features],
            [lost_features]
        )[0][0]

        if similarity > best_similarity:
            best_similarity = similarity
            best_item = item

    return best_item, float(best_similarity)
