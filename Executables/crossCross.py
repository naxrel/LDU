import unicodedata

def keyCreation(key, salt, sugar):
    """
    Args:
        key (string): main key
        salt (string): add more unique values to the key
        sugar (string): add more unique values to the key
    Returns:
        list: trueKey  
    """
    
    #merging the key with cross method
    originalKeyList = list(key)
    saltList = list(salt)
    sugarList = list(sugar)
    
    originalKeyEmpty = False
    saltEmpty = False
    sugarEmpty = False

    originalKeyIndex = 0
    saltIndex = 0
    sugarIndex = 0

    keyList = []
    keyListIndex = []

    generationIter = 0
    
    #Merging key using Cross Method
    while True:
        if generationIter == 0 and originalKeyEmpty == False:
            if originalKeyIndex> len(originalKeyList) - 1 :
                originalKeyEmpty = True
                generationIter += 1
            else:
                keyList.append(originalKeyList[originalKeyIndex])
                originalKeyIndex += 1

        if generationIter == 1:
            if saltIndex > len(saltList) - 1 :
                saltEmpty = True
                generationIter += 1
            else:
                keyList.append(saltList[saltIndex])
                saltIndex += 1

        if generationIter == 2:
            if sugarIndex > len(sugarList) - 1 :
                sugarEmpty = True
            else:
                keyList.append(sugarList[sugarIndex])
                sugarIndex += 1

        generationIter += 1

        if generationIter > 2:
            generationIter = 0

        if originalKeyEmpty == True and saltEmpty == True and sugarEmpty == True:
            break
            
    # [MODIFIKASI] Memuat data unicode yang sudah support enter/tab
    unicodedatass = loadUnicodedata()
    
    for i in keyList:
        if i in unicodedatass:
            keyListIndex.append(unicodedatass.index(i))
        else:
            # [MODIFIKASI] Fallback aman menggunakan Modulo agar index tidak error
            # Mengambil nilai ord (ASCII) dan dimodulo dengan panjang data
            keyListIndex.append(ord(i) % len(unicodedatass))

    #parental key and lucky key
    parentalKey = []
    luckyKey = []
    
    #to help count from back
    reverseHelper = len(keyListIndex) - 1

    for i in range(len(keyListIndex)):
        #parental key generated
        if i + 2 <  len(keyListIndex):
            parentalKey.append(keyListIndex[i] + keyListIndex[i+2])
        else :
            parentalKey.append(keyListIndex[i])
        #lucky key generated
        if i != reverseHelper and reverseHelper > i:
            luckyKey.append(keyListIndex[i] + keyListIndex[reverseHelper])
        else :
            luckyKey.append(keyListIndex[i])
        reverseHelper -=1

    parentalKeyIndex = 0
    luckyKeyIndex = 0

    parentalKeyEmpty = False
    luckyKeyEmpty = False

    trueKey = []
    combineIter = 0

    #Merging parentalKey and luckyKey
    while True: 
        if combineIter == 0:
            if len(parentalKey) - 1 < parentalKeyIndex:
                parentalKeyEmpty = True
                combineIter += 1
            else:
                trueKey.append(parentalKey[parentalKeyIndex])
                parentalKeyIndex+=1
                combineIter += 1

        if combineIter == 1:
            if len(luckyKey) - 1 < luckyKeyIndex:
                luckyKeyEmpty = True
                combineIter = 0
            else:
                trueKey.append(luckyKey[luckyKeyIndex])
                luckyKeyIndex +=1
                combineIter = 0

        if parentalKeyEmpty == True and luckyKeyEmpty == True:
            break
     
    return trueKey

# [MODIFIKASI UTAMA] Fungsi loadUnicodedata diperbarui
def loadUnicodedata():
    unicodeDatas = []
    # [MODIFIKASI] Range diperbesar ke 6000 untuk mencakup lebih banyak simbol
    for code in range(0, 6000): 
        ch = chr(code)
        # [MODIFIKASI] IZINKAN Newline (\n), Tab (\t), Return (\r) untuk Source Code
        if unicodedata.category(ch)[0] != "C" or ch in ['\n', '\t', '\r', '\f']:  
            unicodeDatas.append(ch)
        
    return unicodeDatas

class state:
    def __init__(self, key = "4Z3r0th_", salt = "071>*", sugar = "b3k1nd"):
        self.unicodeDatas = loadUnicodedata()
        self.trueKey = keyCreation(key,salt,sugar)

    def letsEncrypt(self, word = ""):
        """
            #Encrypt the requested sentence (type = str)
        """
        self.word = word
        wordList = list(self.word)
        wordListIndex = []
        
        for i in wordList:
            if i in self.unicodeDatas:
                wordListIndex.append(self.unicodeDatas.index(i))
            else:
                # [MODIFIKASI] Fallback ke spasi jika simbol benar-benar asing, jangan break/crash
                if ' ' in self.unicodeDatas:
                    wordListIndex.append(self.unicodeDatas.index(' '))
                else:
                    wordListIndex.append(0)
        
        iteration = 0
        wordIter = 0

        self.censorWord = []
        
        len_data = len(self.unicodeDatas) # Cache panjang data
        
        #Encryption Begin
        while True:
            if iteration > len(self.trueKey) - 1:
                iteration = 0
            if iteration < len(self.trueKey) - 1:
                # [MODIFIKASI] Gunakan MODULO (%) agar index selalu valid (berputar)
                new_index = (wordListIndex[wordIter] + self.trueKey[iteration]) % len_data
                self.censorWord.append(self.unicodeDatas[new_index])
                wordIter += 1
            
            if wordIter == len(wordList):
                break
            iteration+=1
        return "".join(self.censorWord)
    
    def generatedKeys(self):
        return self.trueKey

class deState:
    #load the unicode data
    def loadUnicodedata(self):
        self.unicodeDatas = loadUnicodedata()

    def __init__(self, key = "4Z3r0th_", salt = "071>*", sugar = "b3k1nd"):
        self.unicodeDatas = loadUnicodedata()
        self.trueKey = keyCreation(key,salt,sugar)

    def letsDecrypt(self, word = ""):
        """
            #Decrypt the requested sentence (type = str)
        """
        self.word = word
        wordList = list(self.word)
        wordListIndex = []
        
        for i in wordList:
            if i in self.unicodeDatas:
                wordListIndex.append(self.unicodeDatas.index(i))
            else:
                # [MODIFIKASI] Handling simbol asing saat dekripsi
                wordListIndex.append(0)
        
        self.decryptedWord = []
        
        iteration = 0
        wordIter = 0
        len_data = len(self.unicodeDatas)
        
        while True:
            if iteration > len(self.trueKey) - 1:
                iteration = 0
            if iteration < len(self.trueKey) - 1:
                # [MODIFIKASI] Gunakan MODULO (%) untuk pengurangan.
                # Python menghandle modulo negatif dengan benar (berputar dari belakang)
                intToChar = (wordListIndex[wordIter] - self.trueKey[iteration]) % len_data
                
                self.decryptedWord.append(self.unicodeDatas[intToChar])
                wordIter += 1
            
            if wordIter == len(wordList):
                break
            iteration+=1
                
        return "".join(self.decryptedWord)
    
    def generatedKeys(self):
        return self.trueKey