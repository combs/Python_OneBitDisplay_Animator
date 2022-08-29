
# // Byte operands for compressing the data
# // The first 2 bits are the type, followed by the counts

OP_MASK = 0xC0
# 1100 0000

OP_SKIPCOPY = 0x00

# 0000 0000

OP_COPYSKIP = 0x40
OP_LONGCOPY = 0x40
# 0100 0000

OP_REPEATSKIP = 0x80
# 1000 0000

OP_REPEAT = 0xC0
# 1100 0000

# 0xc2 11000010
# repeat 3

# 0xb9 10111001
# repeat 8, skip 2


# 0x98 10011000
# repeat 4, skip 0

# 0x38 
# 0011 1000

#  The data is compressed in 3 ways:

#     Skip - the bytes are identical to those of the previous frame
#     Copy - the bytes are different and are copied as-is
#     Repeat - a repeating byte sequence

#     In order to not keep a copy of the display memory on the player, the skip operations just move the write address (cursor position) on the OLED display. The bytes are packed such that the highest 2 bits of each command byte determine the treatment. They are:

#     00SSSCCC - skip+copy (in that order). The 3 bit lengths of each of the skip and copy represent 0-7
#     00000000 - special case (long skip). The next byte is the len (1-256)
#     01CCCSSS - copy+skip (in that order). Same as above
#     01000000 - special case (long copy). The next byte is the len (1-256)


#     1RRRRRRR - Repeat the next byte 1-128 times.

# TODO That doesn't seem to match the real parser. It expects 10RRRRRR
#
#     11RRRSSS - Repeat + skip (in that order).



import argparse, struct, textwrap, time
import numpy


class LongSkip(object):
    def __init__(self, skips=1):
        self.skips = skips
    
    def __repr__(self):
        return "[LongSkip " + str(self.skips) + " bytes]"

class Repeat(object):
    def __init__(self, data, repeats=1):
        self.repeats = repeats
        self.data = data
    
    def __repr__(self):
        return "[Repeat " + str(self.data) + " " + str(self.repeats) + " times]"

class RepeatSkip(object):
    def __init__(self, data, repeats=1, skips=0):
        self.repeats = repeats
        self.skips = skips
        self.data = data
    
    def __repr__(self):
        return "[RepeatSkip " + str(self.data) + " " + str(self.repeats) + " times, skip " + str(self.skips) + "]"

class CopySkip(object):
    def __init__(self, data, copies=1, skips=0):
        self.copies = copies
        self.skips = skips
        self.data = data
    
    def __repr__(self):
        return "[CopySkip output " + str(self.copies) + " bytes: " + str(self.data) + ", skip " + str(self.skips) + "]"

class SkipCopy(object):
    def __init__(self, data, copies=1, skips=0):
        self.copies = copies
        self.skips = skips
        self.data = data
    
    def __repr__(self):
        return "[SkipCopy skip " + str(self.skips) + ", then output " + str(self.copies) + " bytes: " + str(self.data) + "]"

class LongCopy(object):
    def __init__(self, data, copies=1):
        self.copies = copies
        self.data = data
    
    def __repr__(self):
        return "[LongCopy " + str(self.copies) + " bytes: " + str(self.data) + "]"


def parseFrame(compressed, args, index):
    length = len(compressed) - 1
    parsed = []
    future = None
    desired = args.width * args.height // 8

    blocks = 0
    offset = 0

    
    while blocks < desired:


        if index < length:

            this = compressed[index]

            op = this & OP_MASK

            if op==OP_REPEAT:
                # long repeat
                repeats = this & 0b00111111
                datum = compressed[index + 1]
                parsed += [Repeat(data=datum, repeats=repeats)]
                offset = 2
                blocks += repeats
            
            elif op==OP_REPEATSKIP:
                # repeat/skip
                repeats = this & 0b00111000
                repeats = repeats >> 3
                
                skips = this & 0b00000111

                datum = compressed[index + 1]

                parsed += [RepeatSkip(data=datum, repeats=repeats, skips=skips)]

                offset = 2
                blocks += repeats + skips
            
            elif op==OP_SKIPCOPY:

                if this==OP_SKIPCOPY:
                    # long skip
                    skips = compressed[index + 1] + 1
                    parsed += [LongSkip(skips)]
                    offset = 2
                    blocks += skips

                else:
                    # skip/copy
                    skips = this & 0b00111000
                    skips = skips >> 3
                    
                    copies = this & 0b00000111

                    data = compressed[index + 1 : index + 1 + copies]
                    parsed += [SkipCopy(data, copies=copies, skips=skips)]

                    offset = 1 + copies
                    blocks += skips + copies

            elif op==OP_COPYSKIP:

                if this==OP_COPYSKIP:
                    # long copy
                    copies = compressed[index + 1] + 1
                    data = compressed[index + 2 : index + 2 + copies]

                    parsed += [LongCopy(data, copies=copies)]
                    offset = 2 + copies
                    blocks += copies

                else:
                    # copy/skip
                    copies = this & 0b00111000
                    copies = copies >> 3
                    
                    skips = this & 0b00000111

                    data = compressed[index + 1 : index + 1 + copies]
                    parsed += [CopySkip(data, copies=copies, skips=skips)]

                    offset = 1 + copies
                    blocks += skips + copies

            index += offset

            if future==None:
                future = index

            future += offset

            print("Current local offset", offset, "blocks output", blocks, "/", desired, "overall file index", index)
        else:
            raise ValueError("Somehow we have overflowed...")

    return (parsed, future)


if __name__=="__main__":

    parser = argparse.ArgumentParser(description="Parse binary-packed OneBitDisplay animations.")
    parser.add_argument("INPUT")
    # parser.add_argument("-c", "--c", default=True, help="Read C source")
    # parser.add_argument("-b", "--binary", default=False, help="Read binary")
    parser.add_argument("--width", "-sw", default=128, help="Width of screen in pixels.")
    
    parser.add_argument("--height", "-sh", default=64, help="Height of screen in pixels.")
    args = parser.parse_args()
    

    with open(args.INPUT, "rb") as fh:
        compressed = fh.read()

    frames = 0
    index = 0
    output = []

    while True:
        parsed, index = parseFrame(compressed, args, index)
        output += parsed
        print("Frame", frames, "results:", parsed)

        frames += 1
        if index==None:
            break
    
    print("Total decoded bitstream:", output)

