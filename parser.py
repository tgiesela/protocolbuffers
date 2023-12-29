import io
from enum import Enum


class ProtoType(Enum):
    VARINT = 0
    I64 = 1
    LEN = 2
    SGROUP = 3
    EGROUP = 4
    I32 = 5


class ElementKind(Enum):
    NOTSET = 0
    PRIMITIVE = 1,
    GROUP = 2,
    PRIMITIVE_OR_GROUP = 3


def gettype(b):
    prototype = b[0] & 0x07
    return prototype


class ProtoElement:
    def __init__(self):
        self.length_FT = 0
        self.length_LEN = 0
        self.length = 0
        self.field_number = 0
        self.prototype = None
        self.element_kind = ElementKind.NOTSET
        self.data = bytearray()
        self.subElements = {}
        self.max_length = 0
        self.parent = None

    @staticmethod
    def __decode_varint(_bytes: bytearray):
        # _bytes must have been parsed by _extract_varint
        _decodedBytes = bytearray(len(_bytes))
        _varint = 0
        _i = 0
        _int = _bytes[_i]
        _decodedBytes[_i] = _int & 0x007f
        while _i < len(_bytes) - 1:
            _i = _i + 1
            _int = _bytes[_i]
            _decodedBytes[_i] = _int & 0x007f

        # swap the bytes
        _i = 0
        _swapped = bytearray(len(_decodedBytes))
        while _i < len(_decodedBytes):
            _swapped[len(_decodedBytes) - (_i + 1)] = _decodedBytes[_i]
            _i += 1

        for _i in range(len(_bytes)):
            _varint = (_varint << 7) + (_swapped[_i] & 0x7f)

        return _varint

    @staticmethod
    def __decode_fixedint(_bytes: bytearray):
        # _bytes must have been parsed by _extract_varint
        _decodedBytes = bytearray(len(_bytes))
        _varint = 0
        _i = 0
        _decodedBytes[_i] = _bytes[_i]
        while _i < len(_bytes) - 1:
            _i = _i + 1
            _decodedBytes[_i] = _bytes[_i]

        # swap the bytes
        _i = 0
        _swapped = bytearray(len(_decodedBytes))
        while _i < len(_decodedBytes):
            _swapped[len(_decodedBytes) - (_i + 1)] = _decodedBytes[_i]
            _i += 1

        for _i in range(len(_bytes)):
            _varint = (_varint << 8) + (_swapped[_i])

        return _varint

    @staticmethod
    def __extract_varint(f):
        # length of varint determined by msb, as long as this is on, a next byte will follow
        _rawdata = bytearray(10)
        _i = 0
        _rawdata[_i] = int.from_bytes(f.read(1), byteorder='little')
        _int = _rawdata[_i]
        _bytes_processed = 1
        _bit_set = _int >> 7
        while _bit_set:
            _i = _i + 1
            _rawdata[_i] = int.from_bytes(f.read(1), byteorder='little')
            _int = _rawdata[_i]
            _bytes_processed += 1
            _bit_set = _int >> 7

        return _bytes_processed, _rawdata

    def get_int(self):
        if self.prototype == ProtoType.VARINT:
            return self.__decode_varint(self.data[0:self.length])
        else:
            return self.__decode_fixedint(self.data[0:self.length])

    def __store_len(self, f):
        self.length_LEN, _bytes = self.__extract_varint(f)
        self.length = self.__decode_varint(_bytes[0:self.length_LEN])
        if self.length > self.max_length:
            raise RuntimeError("length exceeds max_length")
        self.data = bytearray(self.length)
        self.data = f.read(self.length)

    def __store_group(self, f):
        self.data = bytearray(self.length)
        self.data = f.read(self.length)

    def decode_nr_and_type(self, f):
        self.length_FT, _bytes = self.__extract_varint(f)
        _val = self.__decode_varint(_bytes[0:self.length_FT])
        self.prototype = ProtoType(_val & 0x0007)
        self.field_number = _val >> 3

    def decode(self, f):
        self.decode_nr_and_type(f)
        if self.prototype == ProtoType.I32:
            self.length = 4
            self.data = f.read(4)
            self.element_kind = ElementKind.PRIMITIVE
        elif self.prototype == ProtoType.I64:
            self.length = 8
            self.data = f.read(8)
            self.element_kind = ElementKind.PRIMITIVE
        elif self.prototype == ProtoType.VARINT:
            self.length, self.data = self.__extract_varint(f)
            self.element_kind = ElementKind.PRIMITIVE
        elif ProtoType.LEN:
            self.__store_len(f)
            self.element_kind = ElementKind.PRIMITIVE_OR_GROUP
        else:
            self.__store_group(f)
            self.element_kind = ElementKind.GROUP

    @staticmethod
    def encode_varint(val):
        # val to bytes 7 bits in each byte
        _byteNr = 0
        _valBytes = bytearray(1)
        _byteVal = val & 0x7f
        _valBytes[0] = _byteVal
        val = val >> 7
        while val > 0:
            _valBytes[_byteNr] = _valBytes[_byteNr] | 0x80
            _byteNr += 1
            _byteVal = val & 0x7f
            _valBytes.extend(_byteVal.to_bytes())
            _valBytes[_byteNr] = _byteVal
            val = val >> 7
        return _valBytes

    def encode_fixedint(self, _len, _val):
        _valBytes = bytearray(_len)
        for _i in range(_len):
            _valBytes[_i] = self.data[_i]
        return _valBytes

    def get_TF(self):
        tag = (self.field_number << 3) + self.prototype.value
        return self.encode_varint(tag)

    def get_length(self, _len):
        return self.encode_varint(_len)

    def build(self):
        _msg = bytearray()
        if self.element_kind == ElementKind.GROUP:
            for _element in self.subElements.values():
                _msg.extend(_element.build())
        else:
            _msg = self.data
        _full_msg = bytearray()
        _full_msg.extend(self.get_TF())
        if self.prototype == ProtoType.VARINT:
            # There is no length field
            _full_msg.extend(self.encode_varint(self.get_int()))
        elif self.prototype == ProtoType.I32:
            _full_msg.extend(self.encode_fixedint(4, self.get_int()))
        elif self.prototype == ProtoType.I64:
            _full_msg.extend(self.encode_fixedint(8, self.get_int()))
        else:
            _full_msg.extend((self.get_length(len(_msg))))
            _full_msg.extend(_msg)
        return _full_msg


class ProtoParser:
    def __init__(self):
        self.__tag_dict = None
        self.inputLength = None

    @staticmethod
    def _parse_tag_info(f, maxLength):
        _element = ProtoElement()
        _element.max_length = maxLength
        _element.decode(f)
        return _element

    def _parse_msg(self, f, input_length):
        if input_length <= 0:
            raise RuntimeError("Nothing to process")
        _bytes_processed = 0
        _item = 1
        _dict_for_level = {}
        while _bytes_processed < input_length:
            _element = self._parse_tag_info(f, input_length - _bytes_processed)
            _dict_for_level[_item] = _element
            _bytes_processed += _element.length_LEN + _element.length + _element.length_FT
            if _bytes_processed > input_length or _element.length > input_length:
                raise RuntimeError("Insufficient data")
            if ElementKind(_element.element_kind) == ElementKind.GROUP:
                _element.subElements = self._parse_msg(io.BytesIO(_element.data), _element.length)
                for el in _element.subElements.values():
                    el.parent = _element
            elif ElementKind(_element.element_kind) == ElementKind.PRIMITIVE_OR_GROUP:
                try:
                    _element.subElements = self._parse_msg(io.BytesIO(_element.data), _element.length)
                    if _element.subElements is not None:
                        _element.element_kind = ElementKind.GROUP
                        for el in _element.subElements.values():
                            el.parent = _element
                    else:
                        _element.element_kind = ElementKind.PRIMITIVE
                except:
                    pass
            # else:
            #    return None

            _item += 1
        return _dict_for_level

    def do_parse(self, buf):
        f = io.BytesIO(buf)
        f.seek(0, 2)
        self.inputLength = f.tell()
        f.seek(0, 0)
        self.__tag_dict = self._parse_msg(f, self.inputLength)
        return self.__tag_dict

    def do_build(self):
        _msg = bytearray()
        for element in self.__tag_dict.values():
            _msg.extend(element.build())
        return _msg

    def find_element(self, id) -> ProtoElement | None:
        """
        Finds an element in the parsed elements, returns null if not found
        :param id: string in the form "1.3.2."
        :return: element
        """
        fieldNumbers = id.split('.')
        elDict = self.__tag_dict
        i = 0
        foundEl = None
        while i < len(fieldNumbers) and elDict is not None:
            nr = fieldNumbers[i]
            foundEl = None
            for tag in elDict.values():
                if tag.field_number == int(nr):
                    foundEl = tag
                    break
            if foundEl is not None:
                elDict = foundEl.subElements
                i += 1
            else:
                elDict = None
        if i < len(fieldNumbers):
            return None
        return foundEl

    def set_tags(self, _widevinetags):
        self.__tag_dict = _widevinetags

    @staticmethod
    def new_element(param):
        el = ProtoElement()
        el.field_number = param
        return el

    @staticmethod
    def add_tag(parent_tag, child):
        max_key = -1
        found = False
        key = None
        for tag in parent_tag.subElements:
            if tag > max_key:
                max_key = tag
            el = parent_tag.subElements[tag]
            if el.field_number == child.field_number:
                print("Replacing tag with fieldnumber: ", child.field_number)
                key = tag
                found = True
        child.parent = parent_tag
        if found:
            parent_tag.subElements.update({key: child})
        else:
            parent_tag.subElements.update({max_key + 1: child})

    def get_tags(self):
        return self.__tag_dict


def print_tag(element):
    paragraph = str(element.field_number) + "."
    parent = element.parent
    while parent is not None:
        paragraph = str(parent.field_number) + "." + paragraph
        parent = parent.parent
    indent = ' ' * len(paragraph)

    if element.prototype in [ProtoType.I32, ProtoType.I64, ProtoType.VARINT]:
        print(paragraph + " val: {0}".format(element.get_int()))
    else:
        print(paragraph + " val: {0}".format(element.data[0:element.length]))
    print(indent + " hex: {0}".format(element.data[0:element.length].hex()))
    print(indent + " length: {0}".format(element.length))


def print_tags(tags):
    element: ProtoElement
    for tag in tags:
        element = tags[tag]
        if ElementKind(element.element_kind) == ElementKind.GROUP:
            # print(tabs + "{0}.".format(element.field_number))
            print_tags(element.subElements)
        else:
            print_tag(element)
