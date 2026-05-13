# Document parsing libraries and

This document breaks down some candidate Python libraries and APIs for doing unstructured document parsing, which is the first step of the KG builder pipe line (after fetching the docs of course).

For context, the MVP scope we decided on for this is pdf only, and not worry about images and tables in the pdfs.

## Python libraries for local parsing

### docling

Covers all kinds of document types including pdf, docx, pptx, images, etc, including determining what the format of the doc is. It uses OCR to detect text. It also has the capability to output the parsed doc in a different format, such as markdown. Uses ML models, so would probably run faster with decent HW acceleration. Seems to be the best in terms of quality out of all “intelligent” doc parsing libs/APIs. The API also has functionality for deriving metadata and high level document structure. Well maintained (IBM).

License: MIT

### unstructured.io (OSS Python lib)

It basically has the same functionality as docling. However people online claim that docling is significantly better these days in terms of accuracy. Seems well maintained.

License: Apache 2.0

### pypdf

What we use now. Works only on PDF. It’s pretty fast. It does extract text from tables and adds some special characters to it. When I give this extracted table as text to an LLM, it is able to understand it completely. It can extract images from pdfs, but not interpret them as text. It also has great [functionality for extracting metadata](https://pypdf.readthedocs.io/en/latest/user/metadata.html), without parsing the entire document. And can also extract a document’s structure (nested tree of titles and page numbers). Well maintained.

License: BSD

### pymupdf

[Supports several doc types](https://pymupdf.readthedocs.io/en/latest/about.html), including docx, xlsx, epub, and more. It’s very fast (containing non-Python code). Like docling, it can also output parsed text as markdown, and even help with chunking. Like pypdf, it handles metadata, doc structure well in that it can derive them without parsing the entire doc. It also extracts tables as text with special characters in a way that can be parsed by an LLM. Images are also handled the same way as in pypdf, i.e. it can extract them from a pdf, but there’s no OCR or anything to interpret it. Well maintained.

License: AGPL

### pdfminer.six

Similar to the aforementioned pypdf. The main difference is that it’s able to derive additional, more precise information like font types, and precise character positions and size. This could be useful if we want to capture the exact layout and geometry of the pdf. It cannot be used for editing pdfs. Seems well maintained.

License: MIT

### pdfplumber

Built on top of pdfminer.six, and has some additional convenience functionality that makes it a bit easier to use. Seems to be good at extracting tables (not sure that we need more than py(mu)pdf for that though…). Does not have a major release yet, but seems fairly well maintained.

License: MIT

### python-docx

Works only on docx. Seems pretty fast, and can parse tables. Has fantastic support for navigating the structure of the document, once it’s parsed. Seems to be well maintained.

License: MIT

## Cloud solutions

These are all basically docling, but as hosted cloud services with HTTP APIs.

### LlamaParse

This seems to be fairly popular. Folks online say it’s both faster and has better accuracy than [unstructured.io](http://unstructured.io) (but worse than docling). It has some functionality for deriving metadata and doc layout as well.  
Cost is $0.003 per page.

### unstructured.io (Cloud solution)

Used to be popular, but has fallen out of favor recently due to being slower and having worse accuracy than LlamaParse, and for this reason I did not benchmark it as a cloud solution.  
Start package price is $500/month for 15k pages, and $0.03/page after that.

## Performance benchmark

The benchmark is performed on three different documents, with the relevant libs/APIs. The time is measured in seconds, and approximate over several runs. The benchmark was run on a basic MacBook Pro (by default using the mps device as an accelerator for docling).

### The documents

**Simple 2 page pdf:** The ‘Harry Potter and the Chamber of Secrets Summary’ document, only containing text.

**Complex 72 page pdf:** The paper ‘Challenges and Applications of Large Language Models’. Contains formulas, tables, images.

**Small docx file:** 1-2 pages of straightforward docx, but containing things like tables and dotted lists.

### Results

|  | Simple 2 page pdf | Complex 72 page pdf | Small docx file |
| :---- | :---- | :---- | :---- |
| **docling w/o OCR** | 1.5 \- 2 | 13 \- 14 | 0.39 \- 0.45 |
| **docling w/ OCR** | 4.5 \- 5 | 49 \- 52 | 0.39 \- 0.45 |
| **unstructured.io (lib) w/o OCR** | 0.07 | 4.18 \- 4.22 | 0.07 |
| **unstructured.io (lib) w/ OCR** | 5.2 \- 5.4 | 235 | 0.07 |
| **pypdf** | 0.009 | 1.8 \- 1.9 | n/a |
| **pymupdf** | **0.005** | **0.33** | **0.002** |
| **pdfminer.six** | 0.033 | 3.2 \- 3.3 | n/a |
| **pdfplumber** | 0.165 | 6.6 \- 6.7 | n/a |
| **python-docx** | n/a | n/a | 0.003 |
| **LlamaParse w/o OCR** | 30 (first run), 5 \- 7 (subsequent runs) | 100 (first run), 25 \- 26 (subsequent runs) | 5 \- 7 |
| **LlamaParse w/ OCR** | 30 (first run), 5 \- 7 (subsequent runs) | 138 (first run), 28 \- 30 (subsequent runs) | 18 \- 19 (first run), 5 \- 7 (subsequent runs) |

### Some observations

* pymupdf is the fastest in all categories  
* Using an “intelligent” parser with OCR (optical character recognition of tables, images, etc) is several magnitudes slower than standard doc parsing, as expected  
* docling and unstructured.io is always slower on PDF when using OCR, even if the document only contains text  
* unstructured.io is significantly faster than docling when not using OCR, but significantly slower when using OCR  
* LlamaParse seems to be using caching (sometimes?), so the second time a document is dispatched it is parsed much faster. But that wouldn’t be of great help to us

## Conclusion

Considering our limited MVP scope, just using pymupdf for now seems like the way to go. It’s the most performant, can handle most document formats, and handles metadata, doc structure and tables well. The main thing we would miss out on is using OCR to parse very visual data, like powerpoint docs and images, as well as very precise PDF information like font types. For the former we might consider docling (better accuracy and perf than unstructured.io when using OCR) running on proper HW, or a remote API like LlamaParse in the future.