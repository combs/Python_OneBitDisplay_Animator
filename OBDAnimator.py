
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



from PIL import Image, ImageSequence
import argparse, struct, textwrap, time
import numpy


class Skip(object):
    def __init__(self, skips=1):
        self.skips = skips
    
    def __repr__(self):
        return "[Skip " + str(self.skips) + " bytes]"

class Repeat(object):
    def __init__(self, data, repeats=1):
        self.repeats = repeats
        self.data = data
    
    def __repr__(self):
        return "[Repeat " + str(self.data) + " " + str(self.repeats) + " times]"

def chunked(values, length):
    for i in range(0, len(values), length):
        yield values[i:i + length]

def getVerticalByte(image, x, y):
    
    bools = [ image.getpixel((x, y+i)) for i in range(8)]
    if type(bools[0]) == tuple:
        bools = [ i[0] > 127 for i in bools ]
    else:
        bools = [ i > 127 for i in bools ]

    return numpy.packbits(list(reversed(bools)))

def getFrameBytes(image):
    values = bytearray()
    length = image.width * image.height // 8
    height = image.height

    values = numpy.zeros((length), dtype=numpy.uint8)
    y = 0

    while y < (image.height - 1):
        for x in range(image.width):
            index = ((y // 8 * image.width) + x)
            # print(x, y, index)
            values[index] = getVerticalByte(image, x, y)
            # print(getVerticalByte(image, x, y))
        y += 8
    
    return values

def isNextSmallSkip(deltas, index):
    return (len(deltas) > index + 1) and (isinstance(deltas[index + 1], Skip)) and (deltas[index + 1].skips <= 7)

def isNextSmallCopy(deltas, index):
    return (len(deltas) > index + 1) and (isinstance(deltas[index + 1], int)) and (deltas[index + 1].skips <= 7)

def getNextSmallCopy(deltas, index):
    length = 0
    values = []
    overall = len(deltas)
    # print("getNextSmallCopy index", index, "value", deltas[index + length], type(deltas[index+length]))   

    while (index + length < overall - 1) and (type(deltas[index + length + 1]) == numpy.uint8) and (length < 7):
        # values += [deltas[index + length + 1]]
        length += 1
    values = deltas[index + 1:index + length + 1]
    # print("got values", values)
    return values


def getLargeCopy(deltas, index):
    length = 0
    values = []
    overall = len(deltas)
    # print("getLargeCopy index", index, "value", deltas[index + length], type(deltas[index+length]))   

    while (index + length < overall) and (type(deltas[index + length]) == numpy.uint8) and (length < 256):
        # print("ding", deltas[index + length], length)   
        # values += [deltas[index + length]]
        length += 1
        
    # print("final length", length)
    values = deltas[index:index+length]
    # print("got values", values)
    return values



def generateOpCodes(deltas, pixels):
    output = []

    index = 0
    blocks = 0

    while index < len(deltas):
        item = deltas[index]
        if isinstance(item, Repeat):
            repeats = item.repeats

            if (repeats <= 7):
                # OP_REPEATSKIP, 0-7 0-7
                skips = 0
                if isNextSmallSkip(deltas, index):
                    skips = deltas[index + 1].skips
                    index += 1
                opcode = OP_REPEATSKIP | (repeats << 3) | skips
                print("OP_REPEATSKIP", repeats, "x", item.data, "then", skips, "skips opcode", bin(opcode))
                output += [opcode, item.data]

                index += 1
                blocks += repeats + skips

            else:
                # OP_REPEAT, 1-64
                print("OP_REPEAT", repeats, "x", item.data)
                output += [OP_REPEAT | (repeats - 1), item.data]
                index += 1
                blocks += item.repeats

        
        elif isinstance(item, Skip):
            skips = item.skips
            if skips <= 7:
                # OP_SKIPCOPY, 0-7 0-7, bytes
                copy = getNextSmallCopy(deltas, index)
                copies = len(copy)
                opcode = OP_SKIPCOPY | (skips << 3) | (copies)

                output += [opcode, *copy]
                print("OP_SKIPCOPY", skips, "skips then", copies, "bytes copied", copy, "opcode", bin(opcode))
                index += copies + 1
                blocks += skips + copies
                
            else:
                print("big skip", skips)
                # OP_SKIPCOPY alone, then count 1-256
                output += [OP_SKIPCOPY, (skips - 1)]
                index += 1
                blocks += skips

        else:

            # is value
            large = getLargeCopy(deltas, index)
            small = large[0:8]
            # small = getNextSmallCopy(deltas, index)
            print("copy bytes",large)
            length = len(large)

            if length > 7:
                print("big copy",length)
                output += [OP_LONGCOPY, length - 1, *large]
                index += length
                blocks += length

            elif length:
                skips = 0
                # OP_COPYSKIP
    
                if isNextSmallSkip(deltas, index + length - 1):
                    skips = deltas[index + length].skips
                    index += 1

                opcode = OP_COPYSKIP | (length << 3) | skips

                output += [opcode, *small]
                print("OP_COPYSKIP length", length, "skips", skips, "opcode", bin(opcode))

                index += length
                blocks += length + skips

            else:
                print(item, "end?")
                index += 1

    while blocks * 8 < pixels:
        add = min(256, (pixels - (blocks * 8))//8)
        output += [OP_SKIPCOPY, add - 1]
        blocks += add

        print("padding", add, "blocks")






    return bytearray(output)


def compareFrames(previous, current):
    opcodes = bytearray()

    currbytes = getFrameBytes(current)
    # print(currbytes)

    if previous==None:
        # First frame
        print("First frame")
        # opcodes += generateOpCodes(currbytes, current.width * current.height)
        # for chunk in chunked(currbytes, 256):
        #     opcodes += bytearray([OP_LONGCOPY])
        #     opcodes += bytearray([len(chunk)-1])
        #     opcodes += bytearray(chunk)
        deltas = getFrameBytes(current)
        print(len(deltas))
    else:
        prevbytes = getFrameBytes(previous)
        # print("current", currbytes, "previous", prevbytes)
        deltas = [0] * len(prevbytes)


        print("Pass 1: Computing delta, adding Skips")

        for index in range(len(deltas)):
            # print(currbytes[index], prevbytes[index])
            if currbytes[index] == prevbytes[index]:
                deltas[index] = Skip(1)
            else:
                deltas[index] = currbytes[index]
    
    index = 0
    new = []

    print("Pass 2: Collapsing adjacent Skips")

    while index < len(deltas):
        
        if isinstance(deltas[index], Skip):
            count = deltas[index].skips

            # print("starting count", count)
            while ( ( index < len(deltas) - 1) and (isinstance(deltas[index + 1], Skip))):
                count += 1
                index += 1

                if count > 255:
                    new += [Skip(256)]
                    count -= 256

            # print("final count", count)
            if count > 1:
                new += [Skip(count)]
                # TODO poss efficiency increase: rewind collapses if < 3

            else:
                new += [currbytes[index]]
        else:
            new += [deltas[index]]
        index += 1

    deltas = new

    index = 0
    new = []

    print("Pass 3: Checking for Repeats")


    while index < len(deltas):
        # print(type(deltas[index]))            
        if isinstance(deltas[index], numpy.uint8):
            value = deltas[index]
            count = 1
            # print("Repeat: starting count", count, "for value", value)

            while ( ( index + 1 < len(deltas) - 1) and (deltas[index + 1] == value)):
                count += 1
                index += 1
                
                if count > 63:
                    count -= 64
                    print("Repeat: 64 x", value)
                    new += [Repeat(value, repeats=64)]

            if count > 2:
                print("Repeat:", count, "x", value)
                new += [Repeat(value, repeats=count)]
            else:
                new += [value]
                index -= (count - 1)
        else:
            new += [deltas[index]]
        index += 1

    deltas = new

    print("Pass 4: Generating opcodes")
    
    print(new)

    newOpCodes = generateOpCodes(deltas, current.width * current.height)
    
    print(newOpCodes)   
    
    opcodes += newOpCodes

    return opcodes


def save(output, args):

    binary = args.binary
    c = args.c

    if binary:
        with open(args.OUTPUT, "wb") as fh:
            fh.write(output)
    if c:
        cstring = "#include \"Arduino.h\"\nconst byte bAnimation[] PROGMEM = {\n  "
        index = 1
        for byte in output:

            cstring += "0x{byte:02x},".format(byte=byte)
            if index % 16==0:
                cstring += "\n  "
            index += 1

        cstring = cstring + "\n};"

        # cstring = textwrap.fill(cstring, width=90, drop_whitespace=False)

        with open(args.OUTPUT + ".h", "w") as fh:
            fh.write(cstring) 


if __name__=="__main__":

    parser = argparse.ArgumentParser(description="Compress GIF animations for OneBitDisplay.")
    parser.add_argument("INPUT")
    parser.add_argument("-c", "--c", default=True, help="Output C source")
    parser.add_argument("-b", "--binary", default=False, help="Output binary")
    parser.add_argument("OUTPUT")
    args = parser.parse_args()

    imageObject = Image.open(args.INPUT)
    print(imageObject.is_animated)
    # print(imageObject.n_frames)


    previous = None
    output = bytearray()
    frames = 0

    for frame in ImageSequence.Iterator(imageObject):
        # print(getVerticalByte(frame, 0, 0))

        current = frame.copy()

        output += compareFrames(previous, current)


        previous = frame.copy()
        frames += 1

        if (frames % 1000 == 0):
            save(output, args)
            
        print("finished frame", frames)
        # time.sleep(20)

    save(output, args)