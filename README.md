# Protocol buffers
Small python project to decode and encode Google Protocol buffers without specs.

## Usage

See test-cases for examples.
### Parser
Create an instance of class ProtoParser.
Then call do_parse to parse the buffer.
Finally call print_tags to print the contents.

### Builder
Create an instance of class ProtoParser.
Then call add_tag to add a tag to a specific field.
Finally call do_build, to build the structure.
