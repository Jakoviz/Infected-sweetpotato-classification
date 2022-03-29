# %%
import os
from torch.utils.data import DataLoader
from dataloaders.csv_data_loader import CSVDataLoader
from models.resnet import resnet18
from models.vision_transformer import VisionTransformer
from dotenv import load_dotenv
import matplotlib.pyplot as plt
from torchvision import transforms, datasets
import torch
import torch.optim as optim
import torch.nn.functional as F
import pathlib
from sklearn.metrics import confusion_matrix
import seaborn as sn
import pandas as pd
import numpy as np
import torchvision
from utils.image_utils import img_to_patch

# %%

load_dotenv()

DATA_FOLDER_PATH = os.getenv("DATA_FOLDER_PATH")
PLANT_SPLIT_MASTER_PATH = os.path.join(DATA_FOLDER_PATH, "plant_data_split_master.csv")

#--- hyperparameters ---
N_EPOCHS = 10
BATCH_SIZE_TRAIN = 64
BATCH_SIZE_TEST = 64
LR = 0.01
NUM_CLASSES = 2

# %%

data_transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.RandomRotation(180),
    transforms.Resize((256, 256)),
    transforms.ToTensor(),
    # Values aquired from dataloaders/plant_master_dataset_stats.py
    transforms.Normalize(mean=[0.09872966, 0.11726899, 0.06568969],
                         std=[0.1219357, 0.14506954, 0.08257045])
])

plant_master_dataset = CSVDataLoader(
  csv_file=PLANT_SPLIT_MASTER_PATH, 
  root_dir=DATA_FOLDER_PATH,
  image_path_col="Split masked image path",
  label_col="Label",
  transform=data_transform
)

train_size = int(0.85 * len(plant_master_dataset))
test_size = len(plant_master_dataset) - train_size

train_dataset, test_dataset = torch.utils.data.random_split(plant_master_dataset, [train_size, test_size])

train_plant_dataloader = DataLoader(train_dataset, batch_size=BATCH_SIZE_TRAIN, shuffle=True, num_workers=0)
test_plant_dataloader = DataLoader(test_dataset, batch_size=BATCH_SIZE_TEST, shuffle=False, num_workers=0)

#%% visualize some patches
NUM_IMAGES = 4
train_images = torch.stack([train_dataset[idx]['image'] for idx in range(NUM_IMAGES)], dim=0)

img_patches = img_to_patch(train_images, patch_size=32, flatten_channels=False)

fig, ax = plt.subplots(train_images.shape[0], 1, figsize=(14,3))
fig.suptitle("Images as input sequences of patches")
for i in range(train_images.shape[0]):
    img_grid = torchvision.utils.make_grid(img_patches[i], nrow=64, normalize=True, pad_value=0.9)
    img_grid = img_grid.permute(1, 2, 0)
    ax[i].imshow(img_grid)
    ax[i].axis('off')
plt.show()
plt.close()

#%%

if torch.cuda.is_available():
    device = torch.device('cuda')
else:
    device = torch.device('cpu')

# resnet18_model = resnet18(num_classes=NUM_CLASSES).to(device)
model = VisionTransformer(
    embed_dim=256,
    hidden_dim=512,
    num_heads=8,
    num_layers=6,
    patch_size=32,
    num_channels=3,
    num_patches=64,  # with patch size 32
    num_classes=2,
    dropout=0.2
)

# optimizer = optim.SGD(resnet18_model.parameters(), lr=LR, momentum=0.75)
optimizer = optim.AdamW(model.parameters(), lr=3e-4)
loss_function = torch.nn.CrossEntropyLoss()

# %%

# training

training_losses = []
training_accuracies = []
train_batches = []

for epoch in range(N_EPOCHS):
    total_train_loss = 0
    train_correct = 0
    total = 0

    for batch_num, batch in enumerate(train_plant_dataloader):
        data, target = batch['image'].to(device), batch['label'].to(device)

        # For binary classification, transform labels to one-vs-rest
        target = target.eq(3).type(torch.int64)

        optimizer.zero_grad()

        output = model(data)

        train_loss = loss_function(output, target)
        train_loss.backward()
        optimizer.step()
        
        pred = output.max(1, keepdim=True)[1]

        correct = pred.eq(target.view_as(pred)).sum().item()
        train_correct += correct
        total += data.shape[0]
        total_train_loss += train_loss.item()

        # if batch_num == len(train_plant_dataloader) - 1:
        print('Training: Epoch %d - Batch %d/%d: Loss: %.4f | Train Acc: %.3f%% (%d/%d)' % 
                (epoch, batch_num + 1, len(train_plant_dataloader), train_loss / (batch_num + 1), 
                100. * train_correct / total, train_correct, total))

    # Training loss average for all batches
    training_losses.append(total_train_loss / len(train_plant_dataloader))        
    training_accuracies.append((100. * train_correct / total))

plt.plot(range(N_EPOCHS), training_losses, label = "Training loss")
plt.xlabel('epoch')
plt.ylabel('loss')
plt.title('Loss')
plt.legend()
plt.show()

plt.plot(range(N_EPOCHS), training_accuracies, label = "Training accuracy")
plt.xlabel('epoch')
plt.ylabel('accuracy')
plt.title('Accuracy')
plt.legend()
plt.show()

# %%

# test
test_loss = 0
test_correct = 0
total = 0

with torch.no_grad():
    for batch_num, batch in enumerate(test_plant_dataloader):
        data, target = batch['image'].to(device), batch['label'].to(device)

        # For binary classification, transform labels to one-vs-rest
        target = target.eq(3).type(torch.int64)

        output = model(data)
        test_loss += loss_function(output, target).item()

        pred = output.max(1, keepdim=True)[1]

        correct = pred.eq(target.view_as(pred)).sum().item()
        test_correct += correct
        total += data.shape[0]

        test_loss /= len(test_plant_dataloader.dataset)

print("Final test score: Loss: %.4f, Accuracy: %.3f%%" % (test_loss, (100. * test_correct / total)))

# %%

# Store the model in the current path
# CURRENT_PATH = pathlib.Path(__file__).parent.resolve()
# torch.save(resnet18_model.state_dict(), os.path.join(CURRENT_PATH, "resnet18.pt"))

# %%

y_pred = []
y_true = []

with torch.no_grad():
    for batch_num, batch in enumerate(test_plant_dataloader):
        data, target = batch['image'].to(device), batch['label'].to(device)

        # For binary classification, transform labels to one-vs-rest
        target = target.eq(3).type(torch.int64)

        output = model(data)
        output = output.max(1, keepdim=True)[1]

        output = torch.flatten(output).cpu().numpy()
        y_pred.extend(output)
        
        target = target.cpu().numpy()
        y_true.extend(target)


# Multi-class labels for confusion matrix
# labels = ('CSV', 'FMV', 'Healthy', 'VD')

# Binary labels for confusion matrix
labels = ('Non-VD', 'VD')

# Build confusion matrix
cf_matrix = confusion_matrix(y_true, y_pred)

df_cm = pd.DataFrame(
    cf_matrix/np.sum(cf_matrix), 
    index = [i for i in labels],
    columns = [i for i in labels]
)
plt.figure(figsize = (12,7))

sn.heatmap(df_cm, annot=True)
# %%