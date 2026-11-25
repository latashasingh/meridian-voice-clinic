<div align="center">

# 🦴 SpineAI
### Automated Lumbar Spine MRI Analysis using UNet++

*A deep learning pipeline for precise multiclass segmentation of lumbar spine structures from MRI scans*

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/latashasingh43-commits/SpineAI--Automated-Lumber-Spine-MRI-Analysis-using-UNet-/blob/main/UNetPlusPlus_Optimized_(3)_(1)%20(2).ipynb)
[![Open in NBViewer](https://img.shields.io/badge/Open-NBViewer-orange?logo=jupyter)](https://nbviewer.org/github/latashasingh43-commits/SpineAI--Automated-Lumber-Spine-MRI-Analysis-using-UNet-/blob/main/UNetPlusPlus_Optimized_(3)_(1)%20(2).ipynb)
![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?logo=pytorch&logoColor=white)
![Status](https://img.shields.io/badge/Status-Complete-brightgreen)

</div>

---

## 📖 About the Project

Lumbar spine MRI analysis plays a critical role in diagnosing conditions such as **disc herniation**, **spinal stenosis**, and **degenerative disc disease**. Manual segmentation by radiologists is time-consuming, repetitive, and subject to inter-observer variability.

**SpineAI** addresses this by automating multiclass segmentation of spinal structures using a deep convolutional neural network — enabling **faster, more consistent, and reproducible** analysis that can support diagnostic workflows.

---

## 🏗️ Model Architecture

| Component | Details |
|---|---|
| 🧠 Architecture | UNet++ (Nested U-Net) |
| 🔍 Encoder Backbone | EfficientNet-B4 (ImageNet pretrained) |
| 🎯 Task | Multiclass Semantic Segmentation |
| ⚡ Framework | PyTorch |
| 📐 Training Strategy | Early stopping + Best-model checkpointing based on validation Dice |

The UNet++ architecture introduces nested, dense skip connections between encoder and decoder sub-networks, allowing the model to capture fine-grained anatomical boundaries — essential for accurately distinguishing closely packed spinal structures in MRI scans. The EfficientNet-B4 encoder provides a strong, compute-efficient feature extraction backbone pretrained on ImageNet.

---

## ⚙️ Tech Stack

`Python` &nbsp;`PyTorch` &nbsp;`UNet++` &nbsp;`EfficientNet-B4` &nbsp;`OpenCV` &nbsp;`NumPy` &nbsp;`Pandas` &nbsp;`Matplotlib`

---

## ✨ Key Features

- 🔧 **Custom preprocessing pipeline** for MRI scan normalization and augmentation
- 🧬 **UNet++ with EfficientNet-B4 encoder** for enhanced multiscale feature extraction
- 📈 **Robust training loop** with live Dice/Loss tracking, early stopping, and automatic best-model checkpointing
- 🖼️ **Qualitative visualizations** comparing predicted segmentation masks against ground truth
- 📊 **Comprehensive evaluation** with Dice Score, IoU, Pixel Accuracy, and confusion matrix analysis
- 🚀 Clean, modular, and reproducible notebook workflow

---

## 📊 Results

Final evaluation on the held-out validation set:

| Metric | Score |
|---|---|
| 🎯 Dice Score | **89.75%** |
| 🔗 IoU / Jaccard Index | **86.11%** |
| ✅ Pixel Accuracy | **98.65%** |

> 📌 The model achieved a final validation Dice score of **0.8975** on multiclass lumbar spine structure segmentation, with strong agreement between predicted and ground-truth masks across all classes. Full training curves, per-class confusion matrix, and side-by-side prediction visualizations are available in the notebook — open via the Colab or NBViewer badges above.

---

## 🚀 Getting Started

1. Click the **Open in Colab** badge above
2. Mount your dataset and update the relevant file paths
3. Run all cells sequentially to preprocess data, train the model, and generate evaluation results
4. Visualize predictions in the final evaluation section

---

## 🔮 Future Roadmap

- [ ] Hyperparameter optimization for faster convergence
- [ ] Experiment with alternative encoder backbones (ResNet, ConvNeXt)
- [ ] Build an interactive Streamlit demo for real-time inference
- [ ] Extend to additional spinal structure classes and pathologies

---

## 👩‍💻 Author

**Latasha Singh**

[![GitHub](https://img.shields.io/badge/GitHub-181717?logo=github&logoColor=white)](https://github.com/latashasingh43-commits)

---

<div align="center">

⭐ **If you found this project useful, consider giving it a star!** ⭐

</div>
