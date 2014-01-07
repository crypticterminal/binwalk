import os
import sys
import curses
import string
import platform
import binwalk.core.common as common
from binwalk.core.compat import *
from binwalk.core.module import Module, Option, Kwarg

class HexDiff(Module):


    COLORS = {
        'red'   : '31',
        'green' : '32',
        'blue'  : '34',
    }

    SEPERATORS = ['\\', '/']
    DEFAULT_BLOCK_SIZE = 16

    TITLE = "Binary Diffing"

    CLI = [
            Option(short='W',
                   long='hexdump',
                   kwargs={'enabled' : True},
                   description='Perform a hexdump / diff of a file or files'),
            Option(short='G',
                   long='green',
                   kwargs={'show_green' : True, 'show_blue' : False, 'show_red' : False},
                   description='Only show lines containing bytes that are the same among all files'),
            Option(short='i',
                   long='red',
                   kwargs={'show_red' : True, 'show_blue' : False, 'show_green' : False},
                   description='Only show lines containing bytes that are different among all files'),
            Option(short='U',
                   long='blue',
                   kwargs={'show_blue' : True, 'show_red' : False, 'show_green' : False},
                   description='Only show lines containing bytes that are different among some files'),
            Option(short='w',
                   long='terse',
                   kwargs={'terse' : True},
                   description='Diff all files, but only display a hex dump of the first file'),
    ]
    
    KWARGS = [
            Kwarg(name='show_red', default=True),
            Kwarg(name='show_blue', default=True),
            Kwarg(name='show_green', default=True),
            Kwarg(name='terse', default=False),
            Kwarg(name='enabled', default=False),
    ]

    RESULT_FORMAT = "0x%.8X    %s\n"
    RESULT = ['offset', 'description']
    
    def _no_colorize(self, c, color="red", bold=True):
        return c

    def _colorize(self, c, color="red", bold=True):
        attr = []

        attr.append(self.COLORS[color])
        if bold:
            attr.append('1')

        return "\x1b[%sm%s\x1b[0m" % (';'.join(attr), c)

    def _color_filter(self, data):
        red = '\x1b[' + self.COLORS['red'] + ';'
        green = '\x1b[' + self.COLORS['green'] + ';'
        blue = '\x1b[' + self.COLORS['blue'] + ';'

        if self.show_blue and blue in data:
            return True
        elif self.show_green and green in data:
            return True
        elif self.show_red and red in data:
            return True

        return False

    def hexascii(self, target_data, byte, offset):
        diff_count = 0

        for (fp, data) in iterator(target_data):
            try:
                if data[offset] != byte:
                    diff_count += 1
            except IndexError as e:
                diff_count += 1

        if diff_count == len(target_data)-1:
            color = "red"
        elif diff_count > 0:
            color = "blue"
        else:
            color = "green"

        hexbyte = self.colorize("%.2X" % ord(byte), color)
        
        if byte not in string.printable or byte in string.whitespace:
            byte = "."
        
        asciibyte = self.colorize(byte, color)

        return (hexbyte, asciibyte)

    def diff_files(self, target_files):
        loop_count = 0

        while True:
            line = ""
            done_files = 0
            block_data = {}
            seperator = self.SEPERATORS[loop_count % 2]

            for fp in target_files:
                block_data[fp] = fp.read(self.block)
                if not block_data[fp]:
                    done_files += 1

            # No more data from any of the target files? Done.
            if done_files == len(target_files):
                break

            for fp in target_files:
                hexline = ""
                asciiline = ""

                for i in range(0, self.block):
                    if i >= len(block_data[fp]):
                        hexbyte = "XX"
                        asciibyte = "."
                    else:
                        (hexbyte, asciibyte) = self.hexascii(block_data, block_data[fp][i], i)

                    hexline += "%s " % hexbyte
                    asciiline += "%s" % asciibyte

                line += "%s |%s|" % (hexline, asciiline)

                if self.terse:
                    break

                if fp != target_files[-1]:
                    line += " %s " % seperator

            self.result(offset=(fp.offset + (self.block * loop_count)), description=line)
            loop_count += 1
                
    def init(self):
        # Disable the invalid description auto-filtering feature.
        # This will not affect our own validation.
        self.config.show_invalid = True

        # Set the block size (aka, hexdump line size)
        self.block = self.config.block
        if not self.block:
            self.block = self.DEFAULT_BLOCK_SIZE

        # Build a list of files to hexdiff
        self.hex_target_files = [x for x in iter(self.next_file, None)]

        # Build the header format string
        header_width = (self.block * 4) + 2
        if self.terse:
            file_count = 1
        else:
            file_count = len(self.hex_target_files)
        self.HEADER_FORMAT = "OFFSET        " + ("%%-%ds   " % header_width) * file_count

        # Build the header argument list
        self.HEADER = [fp.name for fp in self.hex_target_files]
        if self.terse and len(self.HEADER) > 1:
            self.HEADER = self.HEADER[0]

        # Set up the tty for colorization, if it is supported
        if hasattr(sys.stderr, 'isatty') and sys.stderr.isatty() and platform.system() != 'Windows':
            curses.setupterm()
            self.colorize = self._colorize
        else:
            self.colorize = self._no_colorize

    def validate(self, result):
        result.valid = self._color_filter(result.description)

    def run(self):
        if self.hex_target_files:
            self.header()
            self.diff_files(self.hex_target_files)
            self.footer()

