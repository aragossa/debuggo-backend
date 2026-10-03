# Sample files for the `upload_file` step action

A step refers to a file by name: `action = upload_file`, `element_path` = the
`<input type="file">`, `value` = `sample.txt`. The files are copied into the backend
image and sent to the browser container by Selenium at upload time.

After adding a file here, add its name to the `upload_file` line of the action lists
in `Utils/AIHelper/HtmlAnalyzer.py` and `Utils/AIHelper/AIHelper.py`, or the model
will not know about it.
