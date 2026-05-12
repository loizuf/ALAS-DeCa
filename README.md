# ALAS, DeCa

A Python script for generating cartograms using linear programming
techniques.

## Demo Videos

A free form exploration and creation of a Demers cartogram for the contiguous US states
[![Creating a Demers Cartogram of the contiguous US states with "ALAS, DeCa"](https://img.youtube.com/vi/jCOi9yPnwns/maxresdefault.jpg)](https://youtu.be/jCOi9yPnwns)

A detailed walk through of the case study explained in the CCCG 2026 submission 
[![ALAS, DeCa — A case study walk through](https://img.youtube.com/vi/kY48jtvkVkg/maxresdefault.jpg)](https://youtu.be/kY48jtvkVkg)


## Requirements

-   Python 3.8 or higher\
-   Dependencies (see `requirements.txt`):
    -   PuLP\
    -   tkinter *(usually included with standard Python installations)*

## Setup

### 1. Clone the repository

``` bash
git clone https://github.com/yourusername/alasdeca.git
cd alasdeca
```

### 2. Create a virtual environment

**Linux / macOS:**

``` bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**

``` bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

``` bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Running the Script

``` bash
python alasdeca.py
```

## Notes

-   `tkinter` is included with most Python installations, but if it is
    missing:

    **Ubuntu / Debian:**

    ``` bash
    sudo apt-get install python3-tk
    ```

    **macOS (Homebrew Python):**

    ``` bash
    brew install python-tk
    ```

-   PuLP uses a default solver (CBC) that should work out of the box.\
    Advanced configurations may require installing additional solvers.

-   The data available in this repository is largely synthetic and only sed as an example. This implementation is still a prototype and lacks proper normalization of loaded data, therefore arbitrary data imported into the tool might not be visualied properly.

## Project Structure

    .
    ├── alasdeca.py
    ├── requirements.txt
    └── README.md

## License

GNU General Public License 3
