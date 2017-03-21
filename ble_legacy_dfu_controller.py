# DFU Opcodes
class Commands:
    START_DFU                    = 1
    INITIALIZE_DFU               = 2
    RECEIVE_FIRMWARE_IMAGE       = 3
    VALIDATE_FIRMWARE_IMAGE      = 4
    ACTIVATE_FIRMWARE_AND_RESET  = 5
    SYSTEM_RESET                 = 6
    PKT_RCPT_NOTIF_REQ           = 8

# DFU Procedures values
DFU_proc_to_str = {
    "01" : "START",
    "02" : "INIT",
    "03" : "RECEIVE_APP",
    "04" : "VALIDATE",
    "08" : "PKT_RCPT_REQ",
}

# DFU Operations values
DFU_oper_to_str = {
    "01" : "START_DFU",
    "02" : "RECEIVE_INIT",
    "03" : "RECEIVE_FW",
    "04" : "VALIDATE",
    "05" : "ACTIVATE_N_RESET",
    "06" : "SYS_RESET",
    "07" : "IMAGE_SIZE_REQ",
    "08" : "PKT_RCPT_REQ",
    "10" : "RESPONSE",
    "11" : "PKT_RCPT_NOTIF",
}

# DFU Status values
DFU_status_to_str = {
    "01" : "SUCCESS",
    "02" : "invalidALID_STATE",
    "03" : "NOT_SUPPORTED",
    "04" : "DATA_SIZE",
    "05" : "CRC_ERROR",
    "06" : "OPER_FAILED",
}

class UUID:
    CCCD                = "00002902-0000-1000-8000-00805f9b34fb"
    DFU_Control_Point   = " -1212-efde-1523-785feabcd123"
    DFU_Packet          = "00001532-1212-efde-1523-785feabcd123"
    DFU_Version         = "00001534-1212-efde-1523-785feabcd123"

"""
------------------------------------------------------------------------------
 Convert a number into an array of 4 bytes (LSB).
 This has been modified to prepend 8 zero bytes per the new DFU spec.
------------------------------------------------------------------------------
"""
def convert_uint32_to_array(value):
    return [0,0,0,0,0,0,0,0,
           (value >> 0  & 0xFF),
           (value >> 8  & 0xFF),
           (value >> 16 & 0xFF),
           (value >> 24 & 0xFF)
    ]

"""
------------------------------------------------------------------------------
 Convert a number into an array of 2 bytes (LSB).
------------------------------------------------------------------------------
"""
def convert_uint16_to_array(value):
    return [
        (value >> 0 & 0xFF),
        (value >> 8 & 0xFF)
    ]

"""
------------------------------------------------------------------------------

------------------------------------------------------------------------------
"""
def convert_array_to_hex_string(arr):
    hex_str = ""
    for val in arr:
        if val > 255:
            raise Exception("Value is greater than it is possible to represent with one byte")
        hex_str += "%02x" % val

    return hex_str

# Print a nice console progress bar
def printProgress (iteration, total, prefix = '', suffix = '', decimals = 1, barLength = 100):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        barLength   - Optional  : character length of bar (Int)
    """
    formatStr       = "{0:." + str(decimals) + "f}"
    percents        = formatStr.format(100 * (iteration / float(total)))
    filledLength    = int(round(barLength * iteration / float(total)))
    bar             = 'x' * filledLength + '-' * (barLength - filledLength)
    sys.stdout.write('\r%s |%s| %s%s %s (%d of %d bytes)' % (prefix, bar, percents, '%', suffix, iteration, total)),
    if iteration == total:
        sys.stdout.write('\n')
    sys.stdout.flush()        

def getHandle(ble_connection, uuid):
    print "getHandle " + uuid
    in_characteristic = True
    ble_connection.before = ""
    ble_connection.sendline('characteristics')
    try:
        ble_connection.expect([uuid], timeout=2)
        handles = re.findall(r"char value handle: 0x..(..)", ble_connection.before)
        print handles
        ble_connection.before = ""
        ble_connection.buffer = ""
    except pexpect.TIMEOUT, e:
        in_characteristic = False

    if not in_characteristic:
        ble_connection.sendline('char-desc')
        try:
            ble_connection.expect([uuid], timeout=2)
            handles = re.findall(r"0x..(..)", ble_connection.before)
            print handles
            ble_connection.before = ""
            ble_connection.buffer = ""
        except pexpect.TIMEOUT, e:
            return False

    if len(handles) > 0:
        return handles[-1]
    else:
        return False


"""
------------------------------------------------------------------------------
 Define the BleDfuServer class
------------------------------------------------------------------------------
"""
class BleDfuServer(object):
    """
    #--------------------------------------------------------------------------
    # Adjust these handle values to your peripheral device requirements.
    #--------------------------------------------------------------------------
    """
    ctrlpt_handle      = 0x10
    ctrlpt_cccd_handle = 0x11
    data_handle        = 0x0e

    pkt_receipt_interval = 5
    pkt_payload_size     = 20

    """
    --------------------------------------------------------------------------
    
    --------------------------------------------------------------------------
    """
    def __init__(self, target_mac, hexfile_path, datfile_path):
        
        self.target_mac = target_mac
        
        self.hexfile_path = hexfile_path
        self.datfile_path = datfile_path

        self.ble_conn = pexpect.spawn("gatttool -b '%s' -t random --interactive" % target_mac)
        self.ble_conn.delaybeforesend = None

        # remove next line comment for pexpect detail tracing.
        #self.ble_conn.logfile = sys.stdout

    """
    --------------------------------------------------------------------------
     Connect to peripheral device.
    --------------------------------------------------------------------------
    """
    def scan_and_connect(self, verbose=False):
        if verbose: print "scan_and_connect"

        try:
            self.ble_conn.expect('\[LE\]>', timeout=10)
        except pexpect.TIMEOUT, e:
            print "Connect timeout"
            return False

        self.ble_conn.sendline('connect')

        try:
            res = self.ble_conn.expect('.*Connection successful.*', timeout=10)
        except pexpect.TIMEOUT, e:
            print "Connect timeout"
            return False

        return True
        
    """
    --------------------------------------------------------------------------
     Wait for notification to arrive.
     Example format: "Notification handle = 0x0019 value: 10 01 01"
    --------------------------------------------------------------------------
    """
    def _dfu_wait_for_notify(self, verbose=False):

        while True:
            if verbose: print "dfu_wait_for_notify"

            if not self.ble_conn.isalive():
                print "connection not alive"
                return None

            try:
                index = self.ble_conn.expect('Notification handle = .*? \r\n', timeout=30)

            except pexpect.TIMEOUT:
                #
                # The gatttool does not report link-lost directly.
                # The only way found to detect it is monitoring the prompt '[CON]'
                # and if it goes to '[   ]' this indicates the connection has
                # been broken.
                # In order to get a updated prompt string, issue an empty
                # sendline('').  If it contains the '[   ]' string, then
                # raise an exception. Otherwise, if not a link-lost condition,
                # continue to wait.
                #
                self.ble_conn.sendline('')
                string = self.ble_conn.before
                if '[   ]' in string:
                    print 'Connection lost! '
                    raise Exception('Connection Lost')
                return None

            if index == 0:
                after = self.ble_conn.after
                hxstr = after.split()[3:]
                handle = long(float.fromhex(hxstr[0]))
                return hxstr[2:]

            else:
                print "unexpeced index: {0}".format(index)
                return None

    """
    --------------------------------------------------------------------------
     Parse notification status results
    --------------------------------------------------------------------------
    """
    def _dfu_parse_notify(self, notify, verbose=False):

        if len(notify) < 3:
            print "notify data length error"
            return None

        dfu_oper = notify[0]
        oper_str = DFU_oper_to_str[dfu_oper]

        if verbose: print notify

        if oper_str == "RESPONSE":

            dfu_process = notify[1]
            dfu_status  = notify[2]

            process_str = DFU_proc_to_str[dfu_process]
            status_str  = DFU_status_to_str[dfu_status]

            if verbose: print "oper: {0}, proc: {1}, status: {2}".format(oper_str, process_str, status_str)

            if oper_str == "RESPONSE" and status_str == "SUCCESS":
                return "OK"
            else:
                return "FAIL"

        if oper_str == "PKT_RCPT_NOTIF":

            byte1 = int(notify[4], 16)
            byte2 = int(notify[3], 16)
            byte3 = int(notify[2], 16)
            byte4 = int(notify[1], 16)

            receipt = 0
            receipt = receipt + (byte1 << 24)
            receipt = receipt + (byte2 << 16)
            receipt = receipt + (byte3 << 8)
            receipt = receipt + (byte4 << 0)

            # print "PKT_RCPT: {0:8}".format(receipt) + " of " + str(self.hex_size)
            printProgress(receipt, self.hex_size, prefix = 'Progress:', suffix = 'Complete', barLength = 50)

            return "OK"

    """
    --------------------------------------------------------------------------
     Wait for a notification and parse the response
    --------------------------------------------------------------------------
    """
    def wait_and_parse_notify(self, verbose=False):
        if verbose: print "Waiting for notification"
        notify = self._dfu_wait_for_notify()

        if verbose: print "Parsing notification"
        # Check the notify status.
        dfu_status = self._dfu_parse_notify(notify)
        if dfu_status != "OK":
            raise Exception("bad notification status: {}".format(dfu_status))

    """
    --------------------------------------------------------------------------
     Send two bytes: command + option
    --------------------------------------------------------------------------
    """
    def _dfu_state_set(self, opcode, verbose=False):
        if verbose: print '_dfu_state_set'

        cmd = 'char-write-req 0x%04x %04x' % (self.ctrlpt_handle, opcode)
        if verbose: print cmd
        self.ble_conn.sendline(cmd)

        # Verify that command was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value was written successfully.*', timeout=10)
        except pexpect.TIMEOUT, e:
            print "State timeout"

    #--------------------------------------------------------------------------
    # Send one byte: command
    #--------------------------------------------------------------------------
    def _dfu_state_set_byte(self, opcode, verbose=False):
        cmd = 'char-write-req 0x%04x %02x' % (self.ctrlpt_handle, opcode)
        if verbose: print cmd
        self.ble_conn.sendline(cmd)

        # Verify that command was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value was written successfully.*', timeout=10)
        except pexpect.TIMEOUT, e:
            print "State timeout"

    #--------------------------------------------------------------------------
    # Send 3 bytes: PKT_RCPT_NOTIF_REQ with interval of 10 (0x0a)
    #--------------------------------------------------------------------------
    def _dfu_pkt_rcpt_notif_req(self, verbose=False):

        opcode = 0x080000
        opcode = opcode + (self.pkt_receipt_interval << 8)

        cmd = 'char-write-req 0x%04x %06x' % (self.ctrlpt_handle, opcode)
        if verbose: print cmd
        self.ble_conn.sendline(cmd)

        # Verify that command was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value was written successfully.*', timeout=10)
        except pexpect.TIMEOUT, e:
            print "Send PKT_RCPT_NOTIF_REQ timeout"

    #--------------------------------------------------------------------------
    # Send an array of bytes: request mode
    #--------------------------------------------------------------------------
    def _dfu_data_send_req(self, data_arr, verbose=False):
        hex_str = convert_array_to_hex_string(data_arr)

        if verbose: print '_dfu_data_send_req'
        cmd = 'char-write-req 0x%04x %s' % (self.data_handle, hex_str)
        if verbose: print cmd
        self.ble_conn.sendline(cmd)

        # Verify that data was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value was written successfully.*', timeout=10)
        except pexpect.TIMEOUT, e:
            print "Data timeout"

    #--------------------------------------------------------------------------
    # Send an array of bytes: command mode
    #--------------------------------------------------------------------------
    def _dfu_data_send_cmd(self, data_arr, verbose=False):
        hex_str = convert_array_to_hex_string(data_arr)
        if verbose: print hex_str
        self.ble_conn.sendline('char-write-cmd 0x%04x %s' % (self.data_handle, hex_str))

    #--------------------------------------------------------------------------
    # Enable DFU Control Point CCCD (Notifications)
    #--------------------------------------------------------------------------
    def _dfu_enable_cccd(self, alreadyDfuMode, verbose=False):
    handle=self.ctrlpt_cccd_handle
    if(alreadyDfuMode==False):
       handle=self.ctrlpt_cccd_handle_buttonless
        if verbose: print "_dfu_enable_cccd"

        cmd = 'char-write-req 0x%04x %s' % (self.ctrlpt_cccd_handle, '0100')
        if verbose: print cmd
        self.ble_conn.sendline(cmd)
        #self.ble_conn.sendline('char-write-req 0x%02x %s' % (self.ctrlpt_cccd_handle, cccd_enable_value_hex_string))

        # Verify that CCCD was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value was written successfully.*', timeout=10)
        except pexpect.TIMEOUT, e:
            print "CCCD timeout"

    #--------------------------------------------------------------------------
    # Send the Init info (*.dat file contents) to peripheral device.
    #--------------------------------------------------------------------------
    def _dfu_send_init(self, verbose=False):

        if verbose: print "dfu_send_info"

        # Open the DAT file and create array of its contents
        bin_array = array('B', open(self.datfile_path, 'rb').read())

        # Transmit Init info
        self._dfu_data_send_req(bin_array)

    #--------------------------------------------------------------------------
    # Initialize: 
    #    Hex: read and convert hexfile into bin_array 
    #    Bin: read binfile into bin_array
    #--------------------------------------------------------------------------
    def input_setup(self):

        print "Sending file " + self.hexfile_path + " to " + self.target_mac

        if self.hexfile_path == None:
            raise Exception("input invalid")

        name, extent = os.path.splitext(self.hexfile_path)

        if extent == ".bin":
            self.bin_array = array('B', open(self.hexfile_path, 'rb').read())

            self.hex_size = len(self.bin_array)
            print "bin array size: ", self.hex_size
            return

        if extent == ".hex":
            intelhex = IntelHex(self.hexfile_path)
            self.bin_array = intelhex.tobinarray()
            self.hex_size = len(self.bin_array)
            print "bin array size: ", self.hex_size
            return

        raise Exception("input invalid")
    
    def _dfu_check_mode(self):
        
        self._dfu_get_handles()
        print self.ctrlpt_cccd_handle
        print self.ctrlpt_handle
        print self.data_handle
        
        print "_dfu_check_mode"
        #look for DFU switch characteristic

        #00001531-1212-efde-1523-785feabcd123 DFU Control Point handle:
        #00001534-1212-efde-1523-785feabcd123 DFU Version
        #00002902-0000-1000-8000-00805f9b34fb
        
        resetHandle = getHandle(self.ble_conn, '00001531-1212-efde-1523-785feabcd123')  

        #resetHandle = getHandle(self.ble_conn, 'f5f90005-59f9-11e4-aa15-123b93f75cba')
        #resetHandle = getHandle(self.ble_conn,"00002902-0000-1000-8000-00805f9b34fb")

        
        print "resetHandle " + str(resetHandle)
        
        self.ctrlpt_cccd_handle=None
        
        if not resetHandle:
            # maybe it already is IN DFU mode
            self.ctrlpt_handle = getHandle(self.ble_conn, '00001531-1212-efde-1523-785feabcd123')
            if not self.ctrlpt_handle:
                print "Not in DFU, nor has the toggle characteristic, aborting.."
                return False
        
        if resetHandle or self.ctrlpt_handle:
            if resetHandle:
                print "Switching device into DFU mode"
                cmd = 'char-write-cmd 0x%02s %02x' % (resetHandle, 1)
                self.ble_conn.sendline(cmd)
                time.sleep(0.2)
        
                print "Node is being restarted"
                self.ble_conn.sendline('exit')
                time.sleep(0.2)
                self.ble_conn.kill(0)
        
                # wait for restart
                time.sleep(5)
                print "Reconnecting..."
        
                # reinitialize
                #self.__init__(self.target_mac, self.hexfile_path, self.interface)
                self.__init__(self.target_mac, self.hexfile_path, self.datfile_path)
                #self.__init__(self.target_mac, self.hexfile_path)
                # reconnect
                connected = self.scan_and_connect()
                
                print "connected " + str(connected)
        
                if not connected:
                    return False
        
                return self._dfu_check_mode()
            else:
                print "Node is in DFU mode"
            return True
        else:
        
            return False

    def _dfu_get_handles(self):
        print "_dfu_get_handles"
        #s110
        #self.ctrlpt_cccd_handle = '0e'
        #self.data_handle = '0b'
        
        #s132
        self.ctrlpt_cccd_handle = '10'
        self.data_handle = '0e'
        
        
        ctrlpt_cccd_handle = getHandle(self.ble_conn,"00002902-0000-1000-8000-00805f9b34fb")
        data_handle = getHandle(self.ble_conn,"00001532-1212-efde-1523-785feabcd123")
        
        print "ctrlpt_cccd_handle " + str(ctrlpt_cccd_handle)
        print "data_handle " + str(data_handle)
        
        if ctrlpt_cccd_handle:
            self.ctrlpt_cccd_handle = ctrlpt_cccd_handle
        if data_handle:
            self.data_handle = data_handle
    
    def switch_in_dfu_mode(self, verbose=False):

        #Enable notifications 
        cmd = 'char-write-req 0x%02x %02x' % (self.ctrlpt_cccd_handle, 1)
        if verbose: print cmd
        self.ble_conn.sendline(cmd)

        #Reset the board in DFU mode. After reset the board will be disconnected
        cmd = 'char-write-req 0x%02x 0104' % (self.ctrlpt_handle)
        if verbose: print cmd
        self.ble_conn.sendline(cmd)

        time.sleep(0.5)

        #print  "Send 'START DFU' + Application Command"
        #self._dfu_state_set(0x0104)

        #Reconnect the board.
        ret = self.scan_and_connect(verbose=verbose)
        if verbose: print "Connected " + str(ret)
        

    """
    --------------------------------------------------------------------------
     Send the binary firmware image to peripheral device.
    --------------------------------------------------------------------------
    """
    def dfu_send_image(self, verbose=False):
        if verbose: print "dfu_send_image"

        if not self._check_DFU_mode():
            print "Switching to DFU mode"
            self.switch_in_dfu_mode()   

        print "Enable Notifications in DFU mode"
        self._dfu_enable_cccd(True, verbose=verbose)

        # Send 'START DFU' + Application Command
        self._dfu_state_set(0x0104, verbose=verbose)

        # Transmit binary image size
        print "Sending hex file size"
        hex_size_array_lsb = convert_uint32_to_array(len(self.bin_array))
        self._dfu_data_send_req(hex_size_array_lsb)

        # Wait for response to Image Size
        print "Waiting for Image Size notification"
        self.wait_and_parse_notify(verbose=verbose)

        # Send 'INIT DFU' Command
        self._dfu_state_set(0x0200)

        # Transmit the Init image (DAT).
        self._dfu_send_init()

        # Send 'INIT DFU' + Complete Command
        self._dfu_state_set(0x0201)

        print "Waiting for INIT DFU notification"
        # Wait for INIT DFU notification (indicates flash erase completed)
        self.wait_and_parse_notify(verbose=verbose)

        # Send packet receipt notification interval
        self._dfu_pkt_rcpt_notif_req()

        # Send 'RECEIVE FIRMWARE IMAGE' command to set DFU in firmware receive state. 
        self._dfu_state_set_byte(Commands.RECEIVE_FIRMWARE_IMAGE)

        '''
        Send bin_array contents as as series of packets (burst mode).
        Each segment is pkt_payload_size bytes long.
        For every pkt_receipt_interval sends, wait for notification.
        '''
        segment_count = 0
        segment_total = int(math.ceil(self.hex_size/float(self.pkt_payload_size)))
        time_start = time.time()
        last_send_time = time.time()
        print "Begin DFU"
        for i in range(0, self.hex_size, self.pkt_payload_size):

            segment = self.bin_array[i:i + self.pkt_payload_size]
            self._dfu_data_send_cmd(segment)
            segment_count += 1

            # print "segment #{} of {}, dt = {}".format(segment_count, segment_total, time.time() - last_send_time)
            # last_send_time = time.time()

            if (segment_count == segment_total):
                printProgress(self.hex_size, self.hex_size, prefix = 'Progress:', suffix = 'Complete', barLength = 50)

                duration = time.time() - time_start
                print "\nUpload complete in {} minutes and {} seconds".format(int(duration / 60), int(duration % 60))
                print "segments sent: {}".format(segment_count)
                print "Waiting for DFU complete notification"
                # Wait for DFU complete notification
                self.wait_and_parse_notify(verbose=verbose)

            elif (segment_count % self.pkt_receipt_interval) == 0:
                notify = self._dfu_wait_for_notify()

                if notify == None:
                    raise Exception("no notification received")

                dfu_status = self._dfu_parse_notify(notify)

                if dfu_status == None or dfu_status != "OK":
                    raise Exception("bad notification status: {}".format(dfu_status))
        
        # Send Validate Command
        self._dfu_state_set_byte(Commands.VALIDATE_FIRMWARE_IMAGE)

        print "Waiting for Firmware Validation notification"
        # Wait for Firmware Validation notification
        self.wait_and_parse_notify(verbose=verbose)

        # Wait a bit for copy on the peer to be finished
        time.sleep(1)

        # Send Activate and Reset Command
        print "Activate and reset"
        self._dfu_state_set_byte(Commands.ACTIVATE_FIRMWARE_AND_RESET)
        
        """
        --------------------------------------------------------------------------
            Return True is already in DFU mode
        --------------------------------------------------------------------------
        """
    def _check_DFU_mode(self, verbose=False):
        print "Checking DFU State..."
        res=False
        cmd = 'char-read-uuid %s' % UUID.DFU_Version
        if verbose: print cmd
        self.ble_conn.sendline(cmd)

        # Skip two rows     
        try:
            res = self.ble_conn.expect('handle:.*', timeout=10)
            # res = self.ble_conn.expect('handle:', timeout=10) 
        except pexpect.TIMEOUT, e:
            print "State timeout"
        except:
            pass
        
        msg_ret = self.ble_conn.after

        # print "msg ret = ", msg_ret
        
        if msg_ret.find("value: 08 00")!=-1:        
            res=True
            print "Board already in DFU mode"
        else:
            print "Board needs to switch in DFU mode"

        return res
        
    """
    --------------------------------------------------------------------------
     Disconnect from peer device if not done already and clean up. 
    --------------------------------------------------------------------------
    """
    def disconnect(self):
        self.ble_conn.sendline('exit')
        self.ble_conn.close()