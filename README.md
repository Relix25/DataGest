<a id="readme-top"></a>

[![Contributors](https://img.shields.io/github/contributors/Relix25/DataGest.svg?style=for-the-badge)](https://github.com/Relix25/DataGest/graphs/contributors)
[![Forks](https://img.shields.io/github/forks/Relix25/DataGest.svg?style=for-the-badge)](https://github.com/Relix25/DataGest/network/members)
[![Stargazers](https://img.shields.io/github/stars/Relix25/DataGest.svg?style=for-the-badge)](https://github.com/Relix25/DataGest/stargazers)
[![Issues](https://img.shields.io/github/issues/Relix25/DataGest.svg?style=for-the-badge)](https://github.com/Relix25/DataGest/issues)
[![MIT License](https://img.shields.io/github/license/Relix25/DataGest.svg?style=for-the-badge)](https://github.com/Relix25/DataGest/blob/main/LICENSE)

<br />
<div align="center">
  <a href="https://github.com/Relix25/DataGest">
    <img src="images/logo.png" alt="Logo" width="80" height="80">
  </a>

<h3 align="center">DataGest</h3>

  <p align="center">
    A powerful desktop application and CLI for image dataset versioning, built on top of Git, DVC, and FiftyOne!
    <br />
    <a href="https://github.com/Relix25/DataGest"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/Relix25/DataGest/issues/new?labels=bug&template=bug-report---.md">Report Bug</a>
    ·
    <a href="https://github.com/Relix25/DataGest/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
  </ol>
</details>

## About The Project

DataGest is a robust, cross-platform MLOps workstation designed to solve the "Frankenstein workflow" of Computer Vision data scientists. Instead of juggling between a terminal for DVC, a text editor for Git, and Python scripts for FiftyOne, DataGest unifies everything.

It provides a pure Python Core API that can be consumed either via a headless Command Line Interface (CLI) or a modern, fluid PySide6 Graphical User Interface (GUI). 

**Key Features:**
* **Dataset Versioning:** Seamlessly tracks your images using DVC and your metadata/history using Git.
* **Visual Exploration:** Instantly explore your dataset versions, labels, and bounding boxes using an integrated FiftyOne local server.
* **Cross-Platform:** Runs flawlessly on Windows, macOS, and Linux.
* **Data Quality Gates:** Built-in validation hooks to prevent corrupted or empty datasets from being pushed to your remote storage.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

* [![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
* [![PySide6](https://img.shields.io/badge/PySide6-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://www.qt.io/for-python)
* [![Git](https://img.shields.io/badge/Git-F05032?style=for-the-badge&logo=git&logoColor=white)](https://git-scm.com/)
* [![DVC](https://img.shields.io/badge/DVC-13ADC7?style=for-the-badge&logo=dvc&logoColor=white)](https://dvc.org/)
* [![FiftyOne](https://img.shields.io/badge/FiftyOne-FF6D04?style=for-the-badge&logo=python&logoColor=white)](https://voxel51.com/)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Getting Started

To get a local copy up and running, follow these simple steps.

### Prerequisites

Before you begin, ensure you have met the following requirements:

* **Python:** Version 3.10 or higher installed on your system.
* **pip:** The Python package installer. Update it using:
```sh
  python -m pip install --upgrade pip

```

### Installation

1. Clone the repo
```sh
git clone [https://github.com/Relix25/DataGest.git](https://github.com/Relix25/DataGest.git)

```


2. Navigate to the project directory
```sh
cd DataGest

```


3. Install the required Python packages
```sh
pip install -r requirements.txt

```


4. Run the application (GUI mode)
```sh
python app.py

```



<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Usage

DataGest can be used in two ways: via its modern Desktop GUI or via the headless CLI for automation and server environments.

**CLI Example:**

```sh
# Sync the current dataset with the remote storage
datagest sync my_dataset_id

# View the dataset in FiftyOne
datagest view my_dataset_id

```

*For more examples and detailed API usage, please refer to the [Documentation*](https://www.google.com/search?q=https://github.com/Relix25/DataGest/wiki)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Roadmap

* [x] **v0.5.1** - Initial Windows Architecture & Workspace Managers
* [ ] **v0.6.0 - Core API & CLI Foundation:** Decouple business logic from PySide6, implement cross-platform support, and create headless CLI.
* [ ] **v0.7.0 - UI/UX Modernization:** Replace manual QSS with a modern Design System (Fluent) and vector icons.
* [ ] **v0.8.0 - FiftyOne Integration:** Integrate local background server for instant visual exploration.
* [ ] **v0.9.0 - Remote Sync & Data Hooks:** Real-time Git `--progress` parsing, Pydantic metadata validation, and secure keyring credential management.
* [ ] **v1.0.0 - Production Release:** Internationalization (i18n) and cross-platform executables (PyInstaller).

See the [open issues](https://github.com/Relix25/DataGest/issues) for a full list of proposed features (and known issues).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".
Don't forget to give the project a star!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License

Distributed under the MIT License. See `LICENSE` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contact

Relix25 - [GitHub Profile](https://github.com/Relix25)

Project Link: [https://github.com/Relix25/DataGest](https://github.com/Relix25/DataGest)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Acknowledgments

* [Othneil Drew's Best-README-Template](https://github.com/othneildrew/Best-README-Template) - For the fantastic and comprehensive README boilerplate.
* [Voxel51](https://voxel51.com/) - For FiftyOne open-source computer vision toolset.
* [Iterative](https://dvc.org/) - For Data Version Control (DVC).
* [PySide6 (Qt for Python)](https://www.qt.io/for-python) - For the GUI framework.

<p align="right">(<a href="#readme-top">back to top</a>)</p>
