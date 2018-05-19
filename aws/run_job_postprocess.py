import os, shutil,re,sys,subprocess

def merge(info,tile_height,tile_width):
    f = 'result_'+str(info[0])
    fzip = f+'.zip'
    cmd = 'unzip ' + fzip + ' -d ' + f
    p = subprocess.Popen(cmd.split())
    outz, errz = p.communicate()
    if p.returncode is not 0:
        print "Could not unzip file"
        exit(1)
        
    os.remove(fzip)
    start_row = int(info[1]) * tile_height
    start_col = int(info[2]) * tile_width
    
    mp = open(f + '/mpA',"r")
    mpi = open(f + '/mpiA', "r")
    count = 0
    for number,idx in zip(mp, mpi):
        val = float(number)
        if matrix_profile[start_col+count] > val:
            matrix_profile[start_col+count] = val
            matrix_profile_index[start_col+count] = int(idx) + start_row
        count += 1    
    mp.close()
    mpi.close()
    print "merged " + str(count) +" values"    
    if info[1] != info[2] and self_join:
        mpB = open(f + '/mpB',"r")
        mpiB = open(f + '/mpiB', "r")
        count = 0
        for number,idx in zip(mpB, mpiB):
            val = float(number)
            if matrix_profile[start_row+count] > val:
                matrix_profile[start_row+count] = val
                matrix_profile_index[start_row+count] = int(idx) + start_col
            count += 1    
        mpB.close()
        mpiB.close()
        print "merged " + str(count) +" values"    
        
    shutil.rmtree(f)

def write_result_s3(out_s3_path):
    cmd='zip mp.zip full_matrix_profile.txt'
    p = subprocess.Popen(cmd.split())
    outz, errz = p.communicate()
    if p.returncode is not 0:
        print "ERROR: could not zip file"
        exit(1)

    os.remove('full_matrix_profile.txt')
    cmd='zip mpi.zip full_matrix_profile_index.txt'
    p = subprocess.Popen(cmd.split())
    if p.returncode is not 0:
        print "ERROR: could not zip file"
        exit(1)

    outz, errz = p.communicate()
    os.remove('full_matrix_profile_index.txt')

    for i in range(0,3):
        cmd = 'aws s3 cp mp.zip s3://' + out_s3_path + 'mp.zip'
        p = subprocess.Popen(cmd.split())
        out, err = p.communicate()
        if p.returncode is not 0:
            print "ERROR: copy to s3 failed"
            if i is 2:
                print "retry attempts exceeded! command was " + cmd
                exit(1)
            else:
                print "will retry."
        else:
            break

    for i in range(0,3):
        cmd = 'aws s3 cp mpi.zip s3://' + out_s3_path + 'mpi.zip'
        p = subprocess.Popen(cmd.split())
        out, err = p.communicate()
        if p.returncode is not 0:
            print "ERROR: copy to s3 failed"
            if i is 2:
                print "retry attempts exceeded! command was " + cmd
                exit(1)
            else:
                print "will retry."
        else:
            break


bucket = sys.argv[1]
directory = sys.argv[2]
tile_width = int(sys.argv[3])
tile_height = int(sys.argv[4])
matrix_profile_length = int(sys.argv[5])
self_join = bool(sys.argv[6])
out_s3_path = sys.argv[7]

cmd = 'aws s3 ls --recursive s3://'+bucket+'/'+directory
process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
output, error = process.communicate()

matrix_profile = [float('inf')] * matrix_profile_length
matrix_profile_index = [0] * matrix_profile_length

#Take only the file paths from s3 ls
files = output.split()[3::4];
num_files = len(files)

if num_files == 0:
    print "No s3 files found"
    exit(0)

copy_commands = []
copy_procs = []
fails = {}
for i, line in enumerate(files):
    x = line.split('/')[1]
    print x
    m = re.search('^\w+_(\d)_(\d)\.zip',x)
    info = (i, m.group(1), m.group(2), 'aws s3 cp s3://'+bucket+'/'+directory+'/'+x+' result_'+str(i)+'.zip')
    copy_commands.append(info)
    fails[info] = 0 

cmd = copy_commands.pop(0)
copy_procs.append([cmd, subprocess.Popen(cmd[3].split(), stdout=subprocess.PIPE)])
while len(copy_commands) > 0:
    cmd = copy_commands.pop(0)
    copy_procs.append([cmd, subprocess.Popen(cmd[3].split(), stdout=subprocess.PIPE)])
    x = copy_procs.pop(0)
    p = x[1]
    info = x[0]
    out,err = p.communicate()
    if p.returncode is not 0:
        print "Copy from s3 failed"
        print out
        print err
        print p.returncode
        fails[info] += 1
        if fails[info] > 3:
            print "ERROR: retry attempts exceeded! for command" + str(info[3])
            exit(1)
        else:
            print "will retry"
            copy_commands.append(info)
            continue

    merge(info,tile_height,tile_width)    

#Finish last jobs in the queue   
while len(copy_procs) > 0:
    x = copy_procs.pop(0)
    p = x[1]
    info = x[0]
    out,err = p.communicate()

    if p.returncode is not 0:
        print "Copy from s3 failed"
        print out
        print err
        print p.returncode
        fails[info] += 1
        if fails[info] > 3:
            print "ERROR: retry attempts exceeded! for command" + str(info[3])
            exit(1)
        else:
            print "will retry"
            copy_procs.append([info, subprocess.Popen(info[3].split(), stdout=subprocess.PIPE)])
            continue
    
    merge(info,tile_height,tile_width)


mp = open('full_matrix_profile.txt', "w")
mpi = open('full_matrix_profile_index.txt', "w")

for number, idx in zip(matrix_profile, matrix_profile_index):
    mp.write(str(number) + '\n')
    mpi.write(str(idx) + '\n')

mp.close()
mpi.close()

print "Finished!"
