---
description: These are all of the configuration options for Global Settings.
---

# Global Settings

<details>

<summary>General</summary>

This is some general settings that will be used regardless of which config is loaded.

***

* allow\_insecure\_connections

Setting this to true will allow the program to connect to websites without ssl (insecurely).

***

* user\_agent

The user agent is the signature of your browser, it's how it is represented to websites you connect to. You can google "what is my user agent" to see what yours may be.

***

* proxy

The proxy you want CDL to utilize. Ex. `https://user:pass@ip:port`

***

* flaresolverr

The IP for flaresolverr you want CDL to utilize. Ex. `ip:port`

CDL will fill the rest of the URL.

***

* max\_file\_name\_length

This is the maximum number of characters allowable in a filename.

***

* max\_folder\_name\_length

This is the maximum number of characters allowable in a folder name.

***

* required\_free\_space

This is the amount of free space in gigabytes that the program will stop initiating downloads at.

</details>

<details>

<summary>Rate Limiting Options</summary>

These are limiting options for the program.

***

* connection\_timeout

The number of seconds to wait while connecting to a website before timing out.

***

* download\_attempts

The number of download attempts per file. Regardless of this value, some conditions (such as a 404 HTTP status) will cause a file to not be retried at all.

***

* read\_timeout

The number of seconds to wait while reading data from a website before timing out. If it's a download, it will be retried and won't count against the download\_attempts limit.

***

* rate\_limit

This is the maximum number of requests that can be made by the program per second.

***

* download\_delay

This is the number of seconds to wait between downloads to the same domain.

Some domains have internal limits set by the program, such as Bunkrr, CyberFile, etc.

***

* max\_simultaneous\_downloads

This is the maximum number of files that can be downloaded simultaneously.

***

* max\_simultaneous\_downloads\_per\_domain

This is the maximum number of files that can be downloaded from a single domain simultaneously.

Some domains have internal limits set by the program, such as Bunkrr, CyberFile, etc.


* download\_speed\_limit

This is the max rate of downloading in KB for all downloads combined
Set to  0 or None to disable


</details>

<details>

<summary>Dupe Option</summary>

These are options for enable/disable dupe clean up of files

**What is a current file?**

- a file that was downloaded during the current run
- or a file that were skipped for already existing when dedupe_already_downloaded is true, during the current run


***

* dedupe\_already\_downloaded
Allows files skipped for already existing on the filesystem to be added to the list of current files

***

* delete\_after\_download

This toggles the deduping process, which happens after all downloads have finished
only files in the current files list are compared and deduped across all files in the hash database

***

* hash\_while\_downloading

With this set as True. Files can be hash after each download, rather than all together

***

* keep_new_download
If delete_after_downloading is True, then one of the following effects will happen

1. If enabled then for each hash and size match one current file will be kept on the system

2. If disabled all current files will be deleted if the following is all true
    * The file did not exist on the filesystem prior to the current run
    * keep prev_download is set to true, this ignores if file exists on the filesystem or not
    * The hash must have already existing on the system prior to the current run
***

* keep\_prev\_download
If delete_after_downloading is True, then one of the following will effects happen

1. If enabled then at least one existing previous download will be kept on system
2. If disabled all previous downloads will be deleted

prev downloads are files from the database that match with a hash and size combination from the current file list, and are not part of the current file list


</details>


<details>

<summary>UI Options</summary>

These are the options for controlling the UI of the program

***

* downloading\_item\_limit

This is the limit on the number of items shown in the UI (while downloading) before they are simply added to the overflow number ("and X other files")

***

* refresh\_rate

This is the refresh rate per second for the UI.

***

* scraping\_item\_limit

This is the limit on the number of items shown in the UI (while scraping) before they are simply added to the overflow number ("and X other links")

***

* vi\_mode

This enables vi/vim keybinds while editing/entering text in CDL.

</details>
