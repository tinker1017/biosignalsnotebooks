
"""
List of functions intended to load data (electrophysiological signals) inside the different file
formats generated by OpenSignals.

The existent formats are .h5, .txt and .edf

Available Functions
-------------------
[Public]

load
    Universal function for reading .txt, .h5 and .edf files generated by OpenSignals.
read_header
    Universal function for reading the header of .txt, .h5 and .edf files generated by OpenSignals.

Available Functions
-------------------
[Private]
_load_txt
    Used for reading .txt files generated by OpenSignals.
_load_h5
    Used for reading .h5 files generated by OpenSignals.
_check_shape_and_type
    With this function it is possible to check if the "devices" and "channels" fields of
    load function have the same shape.
_check_chn_type
    Function used for checking weather the elements in "channels" input of load function are
    coincident with the available channels (specified in the acquisition file).
_available_channels
    Intended for the determination of the available channels in each device.
_check_dev_type
    Function used for checking when the "devices" field of load function only contain devices
    used during the acquisition.
_file_type
    Returns the type of the file defined as input.

Observations/Comments
---------------------
None

/\
"""

# =================================================================================================
# ====================================== Import Statements ========================================
# =================================================================================================
import ast
import os
import datetime
import magic
import requests
import mimetypes
import numpy
import wget
import h5py
import shutil
import json
import time
#from .external_packages import pyedflib
from .aux_functions import _is_instance, _filter_keywords

TEMP_PATH = (os.path.abspath(__file__).split(os.path.basename(__file__))[0] +
             "temp\\").replace("\\", "/")


def load(file, channels=None, devices=None, get_header=False, remote=False, **kwargs):
    """
    Universal function for reading .txt, .h5 and .edf (future) files generated by OpenSignals.

    ----------
    Parameters
    ----------
    file : file path or url (for url 'remote' field needs to be True)
        File path.

    devices : list ["mac_address_1" <str>, "mac_address_2" <str>...]
        List of devices selected by the user.

    channels : list [[mac_address_1_channel_1 <int>, mac_address_1_channel_2 <int>...],
                    [mac_address_2_channel_1 <int>...]...]
        From which channels will the data be loaded.

    get_header : boolean
        If true the file header will be returned as one of the function outputs.

    remote : boolean, optional
        If is True, then the file argument is assumed to be a url where the file can be downloaded.

    **kwargs : list of variable keyword arguments.

    Returns
    -------
    out : ndarray or dict, dict (optional)
        Data read from the input file and the header dictionary when get_header is True.
        When more than one device is specified the returned data is organized in a dictionary where
        each mac address of the device defines a key.
    """

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%% Downloading of file %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    if remote is True:
        # if not os.path.exists("tempOST"):
        #     os.makedirs("tempOST")

        # Check if it is a Google Drive link.
        if "drive.google" in file:
            response = requests.get(file)
            content_type = response.headers['content-type']
            extension = mimetypes.guess_extension(content_type)
        else:
            extension = "." + file.split(".")[-1]

        if None not in [TEMP_PATH,
                        datetime.datetime.now().strftime("%Y" + "_" + "%m" + "_" + "%d" +
                                                                 "_" + "%H_%M_%S"),
                        extension]:
            remote_file_path = (TEMP_PATH + "file_" + datetime.datetime.now().strftime("%Y" + "_" + "%m" + "_" + "%d" + "_" + "%H_%M_%S") + extension).replace("\\", "/")
            file = wget.download(file, remote_file_path)
        else:
            file = wget.download(file)


    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%% Verification of file type %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    file_type = _file_type(file)

    # %%%%%%%%%%%%%%% Verification if shape of channels and devices is the same %%%%%%%%%%%%%%%%%%%
    _check_shape_and_type(devices, channels)

    # =============================================================================================
    # ================== Load data accordingly to file type (Read of Header) ======================
    # =============================================================================================

    header = read_header(file)

    # =============================================================================================
    # ========= Verification if the function inputs ("devices" and "channels") are valid ==========
    # =============================================================================================

    dev_list = list(header.keys())  # Device list.
    if devices is None:
        # When None is defined as the value of the devices input then this means that all
        # devices are relevant.
        devices = dev_list
        if channels is not None:
            channels = [channels]

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%% Devices %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    dev_list_standard = _check_dev_type(devices, dev_list)

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%% Channels %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    chn_dict = _available_channels(devices, header)
    chn_list_standard = _check_chn_type(channels, chn_dict)

    # =============================================================================================
    # =========================== Read of Data from acquisition file ==============================
    # =============================================================================================
    data = None
    if file_type in ["txt", "plain", "bat"]:
        data = _load_txt(file, dev_list_standard, chn_list_standard, header, **kwargs)
        if remote is True:
            if extension == None:
                extension = ".txt"
                remote_file_path = "download_file_name" + extension
    elif file_type in ["h5", "x-hdf", "a"]:
        data = _load_h5(file, dev_list_standard, chn_list_standard)
        if remote is True:
            if extension == None:
                extension = ".h5"
                remote_file_path = "download_file_name" + extension
    elif file_type in ["edf", "octet-stream"]:
        raise RuntimeWarning("In the present package version loading data from .edf files is not "
                             "available yet.")

    # =============================================================================================
    # ======================= Clone downloaded file to signal library =============================
    # =============================================================================================
    project_dir = "../../signal_samples"
    if remote is True and os.path.isdir(project_dir):
        devices = list(header.keys())

        # Check the number of devices.
        nbr_devices = len(devices)
        if nbr_devices > 1:
            devices_label = "multi_hub"
        else:
            devices_label = "single_hub"

        # Get the list of used sensors.
        sensor_list = []
        channels_dev_str = ""
        resolutions_str = ""
        comments_str = ""
        for mac_i, mac in enumerate(devices):
            if len(devices) > 1 and mac_i != len(devices) - 1:
                comment_sep = "\n"
                other_sep = "\t"
            else:
                comment_sep = ""
                other_sep = ""
            sensor_list.append(header[mac]["sensor"])
            channels_dev_str += "[" + mac + "] " + str(len(sensor_list[-1])) + other_sep
            resolutions_str += "[" + mac + "] " + str(header[mac]["resolution"][0]) + " bits" + other_sep
            comments_str += "[" + mac + "] " + str(header[mac]["comments"]) + comment_sep

        sensor_list = list(set(numpy.concatenate(sensor_list)))
        # Check if date and sensor_list is in a bytes format.
        date = header[mac]["date"]
        if type(date) is bytes:
            date = date.decode("ascii")

        if type(sensor_list[0]) in [bytes, numpy.bytes_]:
            sensor_list = [item.decode('ascii') for item in sensor_list]

        date = date.replace("-", "_")
        file_extension = remote_file_path.split(".")[-1]

        shutil.copy(remote_file_path, project_dir + "/" + "signal_sample_" +
                    devices_label + "_" + "_".join(sensor_list) + "_" + date + "." + file_extension)

        # Generation of a json file with relevant metadata.
        aux_chn = list(data[mac].keys())[0]
        json_dict = {"Signal Type": " | ".join(sensor_list),
                     "Acquisition Time": time.strftime("%H:%M:%S.0", time.gmtime(len(data[mac][aux_chn]) / int(header[mac]["sampling rate"]))),
                     "Sample Rate": str(header[devices[0]]["sampling rate"]) + " Hz",
                     "Number of Hubs": str(len(devices)),
                     "Number of Channels": channels_dev_str,
                     "Resolutions": resolutions_str,
                     "Observations": comments_str}
        with open(project_dir + "/" + "signal_sample_" + devices_label + "_" +
                  "_".join(sensor_list) + "_" + date + ".json", 'w') as outfile:
            json.dump(json_dict, outfile)

    # =============================================================================================
    # ===================================== Outputs ===============================================
    # =============================================================================================
    if get_header is True:
        out = data, header
    else:
        out = data

    return out


def read_header(file):
    """
    Universal function for reading the header of .txt, .h5 and .edf files generated by OpenSignals.

    ----------
    Parameters
    ----------
    file : file path
        File path.

    Returns
    -------
    out : dict
        Header data read from the input file.

    """

    # =============================================================================================
    # ============================== Identification of File Type ==================================
    # =============================================================================================

    file_type = _file_type(file)

    # =============================================================================================
    # ========================= Read Header accordingly to file type ==============================
    # =============================================================================================

    if file_type in ["txt", "plain", "bat"]:
        file_temp = open(file, "r")
        header = file_temp.readlines()[1]
        file_temp.close()

        # -------------------------- Conversion to dictionary. ------------------------------------
        header = ast.literal_eval(header.split("# ")[1].split("\n")[0])

        # -------------------------- Standardization of Header ------------------------------------
        macs = header.keys()
        col_nbr = 0
        for mac in macs:
            # ------------ Removal of "special", "sensor", "mode" and "position" keys -------------
            del header[mac]["special"]
            #del header[mac]["sensor"]
            del header[mac]["position"]
            del header[mac]["mode"]

            # ---------------- Combination of the information in "label" and "column" -------------
            column_labels = {}
            for chn_nbr, chn in enumerate(header[mac]["channels"]):
                chn_label = header[mac]["label"][chn_nbr]
                column_labels[chn] = col_nbr + numpy.where(numpy.array(header[mac]["column"]) ==
                                                           chn_label)[0][0]
            header[mac]["column labels"] = column_labels

            col_nbr += len(header[mac]["column"])
            del header[mac]["column"]
            del header[mac]["label"]

    elif file_type in ["h5", "x-hdf", "a"]:
        file_temp = h5py.File(file)
        macs = file_temp.keys()

        header = {}
        for mac in macs:
            header[mac] = dict(file_temp.get(mac).attrs.items())
            header[mac]["sensor"] = []
            # --------- Removal of "duration", "keywords", "mode", "nsamples" ... keys ------------
            for key in ["duration", "mode", "keywords", "nsamples", "forcePlatform values",
                        "macaddress"]:
                if key in header[mac].keys():
                    del header[mac][key]
                    # del header[mac]["duration"]
                    # del header[mac]["mode"]
                    # del header[mac]["keywords"]
                    # del header[mac]["nsamples"]
                    # del header[mac]["forcePlatform values"]
                    # del header[mac]["macaddress"]

            # -------------- Inclusion of a field used in .txt files (Convergence) ----------------
            column_labels = {}
            for chn in header[mac]["channels"]:
                chn_label = "channel_" + str(chn)
                column_labels[chn] = chn_label
                header[mac]["sensor"].append(dict(file_temp.get(mac).get("raw").get("channel_" + str(chn)).attrs.items())["sensor"])
            header[mac]["column labels"] = column_labels

        file_temp.close()

    # elif file_type in ["edf", "octet-stream"]:
    #
    #     # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    #     # %%%%%%%%%%%% Code taken from convertEDF function of OpenSignals fileHandler %%%%%%%%%%%%%%
    #     # %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    #
    #     file_temp = pyedflib.EdfReader(file)
    #     # nbrSamples = file_temp.getNSamples()[0]
    #     nbr_signals = file_temp.signals_in_file
    #     file_header = file_temp.getHeader()
    #     start_date = file_header["startdate"]
    #     file_header["equipment"] += "']"
    #     equipment = ast.literal_eval(file_header['equipment'])
    #     equipment = [n.replace(" ", "_") for n in equipment]
    #     headers = file_temp.getSignalHeaders()
    #     header = {}
    #     mac_address_list = []
    #
    #     # ---------------------------------- Mac Address List --------------------------------------
    #     for signal_nbr in numpy.arange(nbr_signals):
    #         config = headers[signal_nbr]
    #         mac_address = config["transducer"].split(",")[0]
    #
    #         if mac_address not in header.keys():
    #             mac_address_list.append(mac_address)
    #             header[mac_address] = {}
    #             header[mac_address]["device name"] = mac_address
    #             header[mac_address]["sync interval"] = 2
    #             header[mac_address]["time"] = start_date.strftime('%H:%M:%S.%f')[:-3]
    #             header[mac_address]["comments"] = ""
    #             header[mac_address]["device connection"] = ""
    #             header[mac_address]["channels"] = []
    #             header[mac_address]["date"] = start_date.strftime('%Y-%m-%d')
    #             header[mac_address]["digital IO"] = []
    #
    #             if "," in config['transducer']:
    #                 header[mac_address]["firmware version"] = int(config['transducer'].
    #                                                               split(",")[1])
    #             else:
    #                 header[mac_address]["firmware version"] = ""
    #
    #             header[mac_address]["device"] = equipment[len(mac_address_list) - 1]
    #             header[mac_address]["sampling rate"] = int(config['sample_rate'])
    #             header[mac_address]["resolution"] = []
    #             header[mac_address]["column labels"] = {}
    #         if "," in config['prefilter']:
    #             header[mac_address]["channels"].append(int(config['prefilter'].split(",")[0]))
    #             header[mac_address]["resolution"].append(int(config['prefilter'].split(",")[1]))

    else:
        raise RuntimeError("The type of the input file does not correspond to the predefined "
                           "formats of OpenSignals")

    return header


def clean_temp():
    """
    Function for cleaning the temporary folder inside the package.

    source:
    https://stackoverflow.com/questions/185936/how-to-delete-the-contents-of-a-folder-in-python
    """

    folder = 'tempOST'
    for the_file in os.listdir(folder):
        file_path = os.path.join(folder, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as exception:
            print(exception)

# ==================================================================================================
# ================================= Private Functions ==============================================
# ==================================================================================================


def _load_txt(file, devices, channels, header, **kwargs):
    """
    Function used for reading .txt files generated by OpenSignals.

    ----------
    Parameters
    ----------
    file : file, str, or pathlib.Path
        File, filename, or generator to read.  If the filename extension is
        ``.gz`` or ``.bz2``, the file is first decompressed. Note that
        generators should return byte strings for Python 3k.

    devices : list ["mac_address_1" <str>, "mac_address_2" <str>...]
        List of devices selected by the user.

    channels : list [[mac_address_1_channel_1 <int>, mac_address_1_channel_2 <int>...],
                    [mac_address_2_channel_1 <int>...]...]
        From which channels will the data be loaded.

    header : dict
        File header with relevant metadata for identifying which columns may be read.

    **kwargs : list of variable keyword arguments. The valid keywords are those used by
               numpy.loadtxt function.

    Returns
    -------
    out_dict : dict
        Data read from the text file.
    """

    # %%%%%%%%%%%%%%%%%%%%%%%%%%% Exclusion of invalid keywords %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    kwargs_txt = _filter_keywords(numpy.loadtxt, kwargs)

    # %%%%%%%%%%%%%%%%%%%%%%%%%% Columns of the selected channels %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    out_dict = {}
    for dev_nbr, device in enumerate(devices):
        out_dict[device] = {}
        columns = []
        for chn in channels[dev_nbr]:
            columns.append(header[device]["column labels"][chn])
            # header[device]["column labels"] contains the olumn of .txt file where the data of
            # channel "chn" is located.
            out_dict[device]["CH" + str(chn)] = numpy.loadtxt(fname=file, usecols=columns,
                                                              **kwargs_txt)

    return out_dict


def _load_h5(file, devices, channels):
    """
    Function used for reading .h5 files generated by OpenSignals.

    ----------
    Parameters
    ----------
    file : file path.
        File Path.

    devices : list ["mac_address_1" <str>, "mac_address_2" <str>...]
        List of devices selected by the user.

    channels : list [[mac_address_1_channel_1 <int>, mac_address_1_channel_2 <int>...],
                    [mac_address_2_channel_1 <int>...]...]
        From which channels will the data be loaded.

    Returns
    -------
    out_dict : dict
        Data read from the h5 file.
    """

    # %%%%%%%%%%%%%%%%%%%%%%%%%%%% Creation of h5py object %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    h5_object = h5py.File(file)

    # %%%%%%%%%%%%%%%%%%%%%%%%% Data of the selected channels %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    out_dict = {}
    for dev_nbr, device in enumerate(devices):
        out_dict[device] = {}
        for chn in channels[dev_nbr]:
            data_temp = list(h5_object.get(device).get("raw").get("channel_" + str(chn)))

            # Conversion of a nested list to a flatten list by list-comprehension
            # The following line is equivalent to:
            # for sublist in h5_data:
            #    for item in sublist:
            #        flat_list.append(item)
            #out_dict[device]["CH" + str(chn)] = [item for sublist in data_temp for item in sublist]
            out_dict[device]["CH" + str(chn)] = numpy.concatenate(data_temp)

    return out_dict


def _check_shape_and_type(devices, channels):
    """
    Function used for checking if the shape of "devices" and "channels" fields of load function
    have the same shape (the number of elements in the list specified in "devices" is equal to
    the number of sublists inside "channels" field).
    Both "devices" and "channels" must be lists.

    ----------
    Parameters
    ----------
    devices : list ["mac_address_1" <str>, "mac_address_2" <str>...]
        List of devices selected by the user.

    channels : list [[mac_address_1_channel_1 <int>, mac_address_1_channel_2 <int>...],
                    [mac_address_2_channel_1 <int>...]...]
        From which channels will the data be loaded.

    Returns
    -------
    An error message when shape or type of the inputs is not valid.
    """

    if isinstance(devices, type(channels)):  # Comparision of type.
        dev_chn_type = type(devices)
        if devices is None:
            pass
        elif dev_chn_type == list:
            # Comparision of the shape.
            if len(devices) == sum(isinstance(i, list) for i in channels):
                # ----------- Verification if all mac addresses are in a string format ------------
                for dev_nbr, device in enumerate(devices):
                    # List element is a string and is one of the available devices.
                    if isinstance(device, str):
                        # ----------- Verification if all specified channels are integers ----------
                        # Each sublist must be composed by integers.
                        for channel in channels[dev_nbr]:
                            if isinstance(channel, int):
                                continue
                            else:
                                raise RuntimeError("At least one of the 'channels' elements is not "
                                                   "an integer")
                    else:
                        raise RuntimeError("At least one of the 'devices' elements is not a mac "
                                           "address string")
            else:
                raise RuntimeError("The shape of devices and channels lists are not the same. The "
                                   "number of sublists in the 'channels' input may be equal to the "
                                   "number of devices specified in 'devices' field.")
        else:
            raise RuntimeError("The chosen data type of 'devices' and 'channels' fields is not "
                               "supported.")

    elif devices is None and _is_instance(int, channels, condition="all"):
        pass

    else:
        raise RuntimeError("The input 'devices' and 'channels' must be of the same type "
                           "(None or list). When only one device is being used is also possible to "
                           "specify None as 'device' input and a list of integers in the 'channel' "
                           "field")


def _check_chn_type(channels, available_channels):
    """
    Function used for checking weather the elements in "channels" input are coincident with the
    available channels.

    ----------
    Parameters
    ----------
    channels : list [[mac_address_1_channel_1 <int>, mac_address_1_channel_2 <int>...],
                    [mac_address_2_channel_1 <int>...]...]
        From which channels will the data be loaded.

    available_channels : dict
        Dictionary with the list of all the available channels per device.

    Returns
    -------
    out : list
        It is returned a list of the selected channels in a standardized format.

    """

    # ------------------------ Definition of constants and variables -------------------------------
    chn_list_standardized = []

    # %%%%%%%%%%%%%%%%%%%%%%%%%%% Fill of "chn_list_standardized" %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    devices = list(available_channels.keys())
    for dev_nbr, device in enumerate(devices):
        if channels is not None:
            sub_unit = channels[dev_nbr]
            for channel in sub_unit:  # Each sublist must be composed by integers.
                if channel in available_channels[devices[dev_nbr]]:
                    continue
                else:
                    raise RuntimeError("At least one of the specified channels is not available in "
                                       "the acquisition file.")
            chn_list_standardized.append(sub_unit)

        else:  # By omission all the channels were selected.
            chn_list_standardized.append(available_channels[device])

    return chn_list_standardized


def _available_channels(devices, header):
    """
    Function used for the determination of the available channels in each device.

    ----------
    Parameters
    ----------
    devices : list ["mac_address_1" <str>, "mac_address_2" <str>...]
        List of devices selected by the user.

    header: dict
        Dictionary that contains auxiliary data of the acquisition.

    Returns
    -------
    out : dict
        Returns a dictionary where each device defines a key and the respective value will be a list
        of the available channels for the device.

    """

    # ------------------------ Definition of constants and variables ------------------------------
    chn_dict = {}

    # %%%%%%%%%%%%%%%%%%%%%% Access to the relevant data in the header %%%%%%%%%%%%%%%%%%%%%%%%%%%%
    for dev in devices:
        chn_dict[dev] = header[dev]["column labels"].keys()

    return chn_dict


def _check_dev_type(devices, dev_list):
    """
    Function used for checking weather the "devices" field only contain devices used during the
    acquisition.

    ----------
    Parameters
    ----------
    devices : list ["mac_address_1" <str>, "mac_address_2" <str>...]
        List of devices selected by the user.

    dev_list : list
        List of available devices in the acquisition file.

    Returns
    -------
    out : list
        Returns a standardized list of devices.

    """

    if devices is not None:
        for device in devices:
            if device in dev_list:  # List element is one of the available devices.
                continue
            else:
                raise RuntimeError("At least one of the specified devices is not available in the "
                                   "acquisition file.")
        out = devices

    else:
        out = dev_list

    return out


def _file_type(file):
    """
    Function intended for identification of the file type.

    ----------
    Parameters
    ----------
    file : file path
        File path.

    Returns
    -------
    out : str
        Identified file type.

    """
    # %%%%%%%%%%%%%%%%%%%%%%%%%%%%% Verification of file type %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    if "." in file:  # File with known extension.
        file_type = file.split(".")[-1]
    else:  # File without known extension.
        file_type = magic.from_file(file, mime=True).split("/")[-1]

    return file_type

# 07/11/2018  00h02m :)
